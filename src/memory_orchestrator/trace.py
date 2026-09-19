"""Immutable JSONL archives with resumable SQLite metadata and bounded body reads.

The source format is one Episode event per UTF-8 JSON line. Original serialized
line offsets and decoded text offsets are deliberately different coordinates.
Memory use is bounded by one declared-size event and a metadata query batch.
"""
from __future__ import annotations

from collections.abc import Mapping
from collections import OrderedDict
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile

from .schemas import DomainError, digest, new_id, now_iso, validate


def _hash_file(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(65536): h.update(block)
    return h.hexdigest()


def _paths(store, manifest):
    identifier = manifest["trace_id"]
    if not re.fullmatch(r"trace_[a-f0-9]{64}", identifier):
        raise DomainError("trace_mismatch", "Invalid archive identity")
    expected = {"raw_path": f"traces/{identifier}.jsonl", "text_path": f"traces/{identifier}.text",
                "index_path": f"traces/{identifier}.sqlite"}
    if any(manifest[k] != value for k, value in expected.items()):
        raise DomainError("trace_mismatch", "Manifest paths differ from host-owned archive locations")
    return {k: store._path(value, create_parent=True) for k, value in expected.items()}


def _limits(limits):
    for key in ("max_events", "max_bytes", "max_event_bytes"):
        if type(limits.get(key)) is not int or limits[key] < 1:
            raise DomainError("trace_budget", f"Explicit positive trace limit {key} is required")
    return limits


def import_trace(store, episode_header, source_path, *, limits):
    _limits(limits)
    header = validate("EpisodeRecord", episode_header)
    if header["events"] or header.get("trace_ref"):
        raise DomainError("trace_header", "Use an episode header without a second event body source")
    source = Path(source_path).absolute()
    store._no_symlinks(source)
    target = store._path("traces", ".capture", create_parent=True)
    fd, temporary = tempfile.mkstemp(prefix=".capture-", dir=target.parent)
    h, length = hashlib.sha256(), 0
    try:
        source_fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(source_fd, "rb") as original, os.fdopen(fd, "wb") as output:
            while block := original.read(65536):
                output.write(block); h.update(block); length += len(block)
            output.flush(); os.fsync(output.fileno())
        identifier = "trace_" + digest([header["project_id"], header["episode_id"], h.hexdigest()])
        manifest = {"trace_id": identifier, "project_id": header["project_id"], "episode_id": header["episode_id"],
            "format": "events-jsonl-v1", "raw_path": f"traces/{identifier}.jsonl", "raw_sha256": h.hexdigest(),
            "byte_length": length, "text_path": f"traces/{identifier}.text",
            "index_path": f"traces/{identifier}.sqlite", "index_version": 1}
        paths = _paths(store, manifest)
        with store._write_lock():
            if paths["raw_path"].exists():
                if _hash_file(paths["raw_path"]) != manifest["raw_sha256"]:
                    raise DomainError("trace_mismatch", "Existing archived bytes changed")
            else:
                os.replace(temporary, paths["raw_path"])
        manifest = validate("TraceManifest", manifest)
        store.put("trace_manifests", identifier, manifest)
        header["trace_ref"] = identifier
        store.add_episode(header)
        return header
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def _connection(path):
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def _initialize(connection):
    connection.executescript("""
      CREATE TABLE IF NOT EXISTS events (
        base_ref TEXT PRIMARY KEY, event_id TEXT UNIQUE, position INTEGER,
        kind TEXT, call_id TEXT, goal_id TEXT, task_id TEXT, task_revision TEXT,
        source_role TEXT, metadata TEXT NOT NULL);
      CREATE INDEX IF NOT EXISTS event_kind ON events(kind,position);
      CREATE INDEX IF NOT EXISTS event_call ON events(call_id);
      CREATE TABLE IF NOT EXISTS resources(base_ref TEXT, resource_ref TEXT, version_ref TEXT);
      CREATE INDEX IF NOT EXISTS resource_ref ON resources(resource_ref,version_ref);
      CREATE TABLE IF NOT EXISTS chunks(start INTEGER PRIMARY KEY, size INTEGER, sha256 TEXT);
      CREATE TABLE IF NOT EXISTS progress(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """)


def ensure_trace_index(store, trace_ref, limits):
    """Advance a fixed source by at most one event/byte batch; return its reader."""
    _limits(limits)
    manifest = validate("TraceManifest", store.get("trace_manifests", trace_ref))
    paths = _paths(store, manifest)
    if paths["raw_path"].stat().st_size != manifest["byte_length"] or _hash_file(paths["raw_path"]) != manifest["raw_sha256"]:
        raise DomainError("trace_mismatch", "Archived source bytes differ from the immutable manifest")
    prior = sorted([validate("TraceIndexCheckpoint", c) for c in store.list("trace_index_checkpoints", manifest["project_id"]) if c["trace_id"] == trace_ref],
                   key=lambda c: (c["next_raw_byte"], c["created_at"]))
    if prior and prior[-1].get("error") and prior[-1]["error"]["code"] != "trace_event_budget":
        raise DomainError("trace_index_invalid", "Source indexing retained a malformed record", prior[-1])
    with store._write_lock():
        if prior:
            last = prior[-1]
            if _hash_file(paths["index_path"]) != last["index_sha256"] or _hash_file(paths["text_path"]) != last["text_sha256"]:
                raise DomainError("trace_mismatch", "Derived index/spool changed outside a recorded indexing batch")
            if last["index_complete"]:
                return TraceReader(store, manifest, paths, last), last
        connection = _connection(paths["index_path"])
        _initialize(connection)
        existing = connection.execute("SELECT value FROM progress WHERE key='state'").fetchone()
        state = json.loads(existing[0]) if existing else {"next_raw_byte": 0, "event_count": 0, "parent_episode_refs": []}
        if prior and state["next_raw_byte"] != prior[-1]["next_raw_byte"]:
            connection.close(); raise DomainError("trace_mismatch", "Checkpoint and index progress disagree")
        if not prior and state["next_raw_byte"]:
            connection.close(); raise DomainError("trace_mismatch", "Unanchored index requires deliberate recovery")
        start = state["next_raw_byte"]
        error, added = None, 0
        # One source record is atomic. A record larger than max_bytes is rejected
        # as a budget gap instead of making a hidden oversized read exception.
        with paths["raw_path"].open("rb") as original, paths["text_path"].open("ab") as spool:
            original.seek(start)
            while added < limits["max_events"] and original.tell() - start < limits["max_bytes"]:
                line_start = original.tell()
                allowance = min(limits["max_event_bytes"], limits["max_bytes"] - (line_start - start))
                line = original.readline(allowance + 1)
                if not line: break
                if len(line) > allowance:
                    if added: original.seek(line_start); break
                    error = {"code": "trace_event_budget", "raw_range": [line_start, line_start + len(line)],
                             "message": "A JSONL event exceeds the declared event/batch byte limit"}; break
                try:
                    event = json.loads(line.decode("utf-8"))
                    # Same event contract as ordinary Episode import, not another schema.
                    header = {**store.get("episodes", manifest["episode_id"]), "events": [event]}
                    validate("EpisodeRecord", header)
                    text = event["text"].encode("utf-8")
                    text_start = spool.tell(); spool.write(text)
                    for offset in range(0, len(text), 1024):
                        chunk = text[offset:offset + 1024]
                        connection.execute("INSERT INTO chunks VALUES(?,?,?)", (text_start + offset, len(chunk), hashlib.sha256(chunk).hexdigest()))
                    from .evidence import _kind, _failure_position, _RECOVERY
                    base = "ev:" + digest([manifest["project_id"], manifest["episode_id"], "event", event["event_id"]])[:24]
                    signal = _failure_position(event['text'])
                    recovery = _RECOVERY.search(event['text'])
                    if signal is None and recovery: signal = recovery.start()
                    metadata = {"base_ref": base, "episode_id": manifest["episode_id"], "event_id": event["event_id"],
                        "kind": _kind(event), "source_kind": event["kind"], "namespace": "event",
                        "raw_ref": event.get("source_ref") or f"episode:{manifest['episode_id']}/event:{event['event_id']}",
                        "raw_hash": digest(event["text"]), "source": header["source"],
                        "position": state["event_count"], "source_event": True,
                        **{k: event.get(k) for k in ("task_revision", "task_id", "goal_id", "source_role", "call_id", "parent_event_id", "parent_episode_id")},
                        "resources": event.get("resources", []), "text_start": text_start, "text_bytes": len(text),
                        "failure_byte": len(event["text"][:signal].encode()) if signal is not None else None,
                        "failure_terms": sorted(set(re.findall(r"\b[A-Z][A-Z0-9_]{2,}(?:ERROR|FAIL|MISMATCH|MISSING)[A-Z0-9_]*\b|\b[A-Z][A-Za-z]+Error\b", event["text"]))),
                        "source_record": {"trace_ref": trace_ref,
                            "raw_range": {"start_byte": line_start, "end_byte_exclusive": original.tell()},
                            "raw_sha256": manifest["raw_sha256"]}}
                    connection.execute("INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?)", (base, event["event_id"], state["event_count"],
                        metadata["kind"], metadata["call_id"], metadata["goal_id"], metadata["task_id"], metadata["task_revision"], metadata["source_role"], json.dumps(metadata)))
                    for resource in metadata["resources"]:
                        connection.execute("INSERT INTO resources VALUES(?,?,?)", (base, resource["ref"], resource["version_ref"]))
                    if metadata["parent_episode_id"] and metadata["parent_episode_id"] not in state["parent_episode_refs"]:
                        state["parent_episode_refs"].append(metadata["parent_episode_id"])
                    state["event_count"] += 1; added += 1; state["next_raw_byte"] = original.tell()
                except (ValueError, UnicodeError, sqlite3.IntegrityError, DomainError) as exc:
                    error = {"code": getattr(exc, "code", "malformed_trace_event"),
                             "raw_range": [line_start, original.tell()], "message": str(exc)}
                    break
            spool.flush(); os.fsync(spool.fileno())
        connection.execute("INSERT OR REPLACE INTO progress VALUES('state',?)", (json.dumps(state),))
        connection.commit(); connection.close()
        checkpoint = {"checkpoint_id": new_id("trace_checkpoint"), "trace_id": trace_ref,
            "project_id": manifest["project_id"], "episode_id": manifest["episode_id"], "raw_sha256": manifest["raw_sha256"],
            "index_version": 1, **state, "index_complete": error is None and state["next_raw_byte"] == manifest["byte_length"],
            "bytes_processed": state["next_raw_byte"] - start, "error": error,
            "index_sha256": _hash_file(paths["index_path"]), "text_sha256": _hash_file(paths["text_path"]), "created_at": now_iso()}
    checkpoint = validate("TraceIndexCheckpoint", checkpoint)
    store.put("trace_index_checkpoints", checkpoint["checkpoint_id"], checkpoint)
    if error: raise DomainError("trace_index_invalid", "JSONL indexing stopped at a retained source range", checkpoint)
    return TraceReader(store, manifest, paths, checkpoint), checkpoint


class TraceReader:
    def __init__(self, store, manifest, paths, checkpoint):
        self.store, self.manifest, self.paths, self.checkpoint = store, manifest, paths, checkpoint
        self.identities = {key: (path.stat().st_dev, path.stat().st_ino, path.stat().st_size, path.stat().st_mtime_ns)
                           for key, path in paths.items()}
        self.stats = {"body_bytes": 0, "range_reads": 0, "metadata_rows": 0}
        self.chunk_cache, self.cache_bytes = OrderedDict(), 0
        self.metadata_cache, self.metadata_bytes = OrderedDict(), 0

    def set_read_budget(self, max_bytes):
        self.cache_bytes = max_bytes // 2
        self.metadata_bytes = max_bytes - self.cache_bytes
        while sum(len(x) for x in self.chunk_cache.values()) > self.cache_bytes:
            self.chunk_cache.popitem(last=False)
        while sum(len(x) for x in self.metadata_cache.values()) > self.metadata_bytes:
            self.metadata_cache.popitem(last=False)

    def check(self):
        _paths(self.store, self.manifest)
        if any((p.stat().st_dev, p.stat().st_ino, p.stat().st_size, p.stat().st_mtime_ns) != self.identities[k]
               for k, p in self.paths.items()):
            raise DomainError("trace_mismatch", "A source/index/spool file changed after opening this reader")

    def rows(self, where="1", params=(), *, limit=None):
        self.check()
        with closing(_connection(self.paths["index_path"])) as connection:
            sql = "SELECT metadata FROM events WHERE " + where + " ORDER BY position"
            if limit is not None: sql += " LIMIT ?"; params = (*params, limit)
            for row in connection.execute(sql, params):
                record = json.loads(row[0]); record["_reader"] = self
                self.stats["metadata_rows"] += 1
                if len(row[0]) <= self.metadata_bytes:
                    self.metadata_cache[record["base_ref"]] = row[0]
                    self.metadata_cache.move_to_end(record["base_ref"])
                    while sum(len(x) for x in self.metadata_cache.values()) > self.metadata_bytes:
                        self.metadata_cache.popitem(last=False)
                yield record

    def get_metadata(self, ref):
        self.check()
        if ref in self.metadata_cache:
            self.metadata_cache.move_to_end(ref)
            record = json.loads(self.metadata_cache[ref]); record["_reader"] = self
            return record
        try: return next(self.rows("base_ref=?", (ref,), limit=1))
        except StopIteration: raise KeyError(ref) from None

    def read_range(self, record, start, end):
        self.check()
        if not 0 <= start <= end <= record["text_bytes"]:
            raise DomainError("unsupported_evidence", "Decoded byte range exceeds the indexed event")
        absolute_start, absolute_end = record["text_start"] + start, record["text_start"] + end
        data = bytearray()
        with closing(_connection(self.paths["index_path"])) as connection, self.paths["text_path"].open("rb") as handle:
            rows = connection.execute("SELECT start,size,sha256 FROM chunks WHERE start < ? AND start+size > ? ORDER BY start",
                                      (absolute_end, absolute_start))
            for offset, size, sha in rows:
                block = self.chunk_cache.get((offset, sha))
                if block is None:
                    handle.seek(offset); block = handle.read(size)
                    self.stats["body_bytes"] += len(block)
                else:
                    self.chunk_cache.move_to_end((offset, sha))
                if hashlib.sha256(block).hexdigest() != sha:
                    raise DomainError("trace_mismatch", "Decoded text chunk changed")
                if size <= self.cache_bytes:
                    self.chunk_cache[(offset, sha)] = block
                    while sum(len(x) for x in self.chunk_cache.values()) > self.cache_bytes:
                        self.chunk_cache.popitem(last=False)
                data.extend(block[max(0, absolute_start-offset):min(size, absolute_end-offset)])
        if len(data) != end-start:
            raise DomainError("trace_mismatch", "Indexed text range has missing bytes")
        self.stats["range_reads"] += 1
        return bytes(data)


class TraceRecords(Mapping):
    """The one mixed in-memory/JSONL registry used by the existing evidence path."""
    def __init__(self, memory, readers): self.memory, self.readers = memory, readers
    def __len__(self): return len(self.memory) + sum(r.checkpoint["event_count"] for r in self.readers)
    def __iter__(self):
        yield from self.memory
        for reader in self.readers:
            for row in reader.rows(): yield row["base_ref"]
    def __getitem__(self, key):
        if key in self.memory: return self.memory[key]
        for reader in self.readers:
            try: return reader.get_metadata(key)
            except KeyError: pass
        raise KeyError(key)
    def values(self):
        yield from self.memory.values()
        for reader in self.readers: yield from reader.rows()
    def items(self):
        for row in self.values(): yield row["base_ref"], row
    def select_metadata(self, query, limit):
        focus = set(query.get("focus", [])); selected = {}
        for ref in focus:
            try: selected[ref] = self[ref]
            except KeyError: continue
        # Query a bounded spread of source positions before touching any body.
        # Do not prefilter all actions before the returns that explain them.
        for row in self.memory.values():
            if len(selected) >= limit: break
            selected.setdefault(row["base_ref"], row)
        from collections import deque
        from .evidence import _temporal_positions
        streams = deque((reader, iter(_temporal_positions(reader.checkpoint['event_count'], limit))) for reader in self.readers)
        while streams and len(selected) < limit:
            reader, positions = streams.popleft()
            try: position = next(positions)
            except StopIteration: continue
            for condition in ("position>=? AND (kind IN ('task','feedback','recovery','counterexample') OR json_extract(metadata,'$.failure_byte') IS NOT NULL)",
                              "position>=?"):
                for row in reader.rows(condition, (position,), limit=1):
                    if len(selected) >= limit: break
                    selected.setdefault(row['base_ref'], row)
                    if row['call_id'] is not None:
                        for other in reader.rows('call_id=?', (row['call_id'],), limit=min(2, limit - len(selected))):
                            selected.setdefault(other['base_ref'], other)
            streams.append((reader, positions))
        return list(selected.values())[:limit]
    def matching(self, *, episode_id=None, call_id=None, resource=None, user_goals=False):
        def matches(row):
            return ((episode_id is None or row["episode_id"] == episode_id)
                and (call_id is None or row["call_id"] == call_id)
                and (not user_goals or row["source_role"] == "user" and row["source_kind"] == "instruction")
                and (resource is None or any(x["ref"] == resource for x in row.get("resources", []))))
        for row in self.memory.values():
            if matches(row): yield row
        for reader in self.readers:
            if episode_id is not None and reader.manifest["episode_id"] != episode_id: continue
            conditions, params = [], []
            if call_id is not None: conditions.append("call_id=?"); params.append(call_id)
            if user_goals: conditions.append("source_role='user' AND kind='task'")
            if resource is not None: conditions.append("base_ref IN (SELECT base_ref FROM resources WHERE resource_ref=?)"); params.append(resource)
            yield from reader.rows(" AND ".join(conditions) or "1", tuple(params))
