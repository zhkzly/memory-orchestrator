"""Local immutable memory records and project-bound Skill snapshots.

The store knows provenance and byte identity, not whether a recalled fact is true
or a Skill caused an outcome. Publication policy belongs to N10; its private CAS
primitive is the only operation here that advances an existing active pointer.
"""

from contextlib import contextmanager
from copy import deepcopy
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import tempfile

from .schemas import DomainError, digest, json_bytes, new_id, now_iso, validate
from .lineage import check_feedback_binding, resolve_episode_source


KINDS = frozenset({
    "episodes", "feedback", "contexts", "relations", "executions", "errors",
    "run_groups", "sampling_inputs", "sampling_batches", "runs", "group_receipts", "assessments", "evidence_packets",
    "experiences", "diagnoses", "learning_cycles", "evaluation_plans",
    "evaluation_inputs", "evaluation_returns", "evaluation_results", "validations",
    "selections", "releases", "usage", "reports", "candidates", "protocols",
    "case_sets", "evaluator_configs", "stage_measurements", "feedback_plans", "baselines",
    "callback_attempts", "callback_returns", "recovery_resolutions", "sampling_segments", "sampling_batch_receipts",
    "trace_manifests", "trace_index_checkpoints", "goal_bindings", "memory_relations", "maintenance_reviews",
    "verification_materials", "verification_plans", "verification_records", "asset_checks", "execution_views",
    "contrast_plans", "contrast_results",
    "experiment_plans", "experiment_steps", "experiment_results",
    "comparison_segments",
})
SCHEMA_KINDS = {
    "episodes": ("EpisodeRecord", "episode_id"),
    "feedback": ("Feedback", "check_id"),
    "run_groups": ("RunGroupPlan", "group_id"),
    "sampling_batches": ("SamplingBatchPlan", "batch_id"),
    "runs": ("RunBundle", "run_id"),
    "assessments": ("TaskAssessment", "assessment_id"),
    "evidence_packets": ("EvidencePacket", "packet_id"),
    "evaluation_plans": ("EvaluationPlan", "plan_id"),
    "evaluation_results": ("EvaluationResult", "request_id"),
    "validations": ("ValidationRecord", "validation_id"),
    "selections": ("SelectionRecord", "selection_id"),
    "releases": ("ReleaseRecord", "release_id"),
    "baselines": ("BaselineRecord", "baseline_id"),
    "feedback_plans": ("FeedbackPlan", "feedback_plan_id"),
    "callback_attempts": ("CallbackAttempt", "attempt_id"),
    "callback_returns": ("CallbackReturn", "attempt_id"),
    "recovery_resolutions": ("RecoveryResolution", "resolution_id"),
    "sampling_segments": ("SamplingSegment", "record_id"),
    "sampling_batch_receipts": ("SamplingBatchReceipt", "receipt_id"),
}


def _string(value, name):
    if not isinstance(value, str) or not value.strip():
        raise DomainError("INVALID_ARGUMENT", f"{name} must be a nonempty string", {"field": name})
    return value


def _same_project(record, project):
    if record.get("project_id") != project:
        raise DomainError("PROJECT_MISMATCH", "Reference belongs to another project",
                          {"expected": project, "actual": record.get("project_id")})


class Store:
    def __init__(self, root):
        if not isinstance(root, (str, os.PathLike)) or not os.fspath(root):
            raise DomainError("INVALID_ARGUMENT", "An explicit storage root is required")
        self.root = Path(os.path.abspath(root))
        self._no_symlinks(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._no_symlinks(self.root)
        root_stat = self.root.stat()
        if not stat.S_ISDIR(root_stat.st_mode):
            raise DomainError("UNSAFE_PATH", "Storage root is not a directory")
        self._root_identity = (root_stat.st_dev, root_stat.st_ino)

    @staticmethod
    def _no_symlinks(path):
        for current in reversed([path, *path.parents]):
            try:
                mode = current.lstat().st_mode
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(mode):
                raise DomainError("UNSAFE_PATH", "Symlink storage paths are not accepted", {"path": str(current)})

    def _check_root(self):
        self._no_symlinks(self.root)
        try:
            current = self.root.stat()
        except FileNotFoundError as exc:
            raise DomainError("STALE_ROOT", "Storage root no longer exists") from exc
        if (current.st_dev, current.st_ino) != self._root_identity:
            raise DomainError("STALE_ROOT", "Storage root was replaced; reopen deliberately")

    def _path(self, *parts, create_parent=False):
        self._check_root()
        path = self.root.joinpath(*parts)
        if not path.is_relative_to(self.root):
            raise DomainError("UNSAFE_PATH", "Path escapes storage root")
        self._no_symlinks(path)
        if create_parent:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._no_symlinks(path)
        return path

    @contextmanager
    def _write_lock(self):
        path = self._path(".write.lock")
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            self._check_root()
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def _read_json(self, path):
        self._check_root()
        self._no_symlinks(path)
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except FileNotFoundError as exc:
            raise DomainError("NOT_FOUND", "Stored object does not exist", {"path": str(path)}) from exc
        except (OSError, ValueError, UnicodeError) as exc:
            raise DomainError("CORRUPT_RECORD", "Cannot read stored JSON",
                              {"path": str(path), "error": str(exc)}) from exc

    def _atomic_write(self, path, value):
        """Same-directory replacement; callers hold the write lock.

        Failure before replacement preserves the old value. An fsync failure
        after replacement is an uncertain commit, reported as such, not success.
        """
        data = json_bytes(value)
        self._check_root()
        self._no_symlinks(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._no_symlinks(path.parent)
        fd, temp_name = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
        committed = False
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            self._check_root()
            self._no_symlinks(path)
            os.replace(temp_name, path)
            committed = True
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except OSError as exc:
            raise DomainError("COMMIT_UNCERTAIN" if committed else "STORAGE_ERROR",
                              "Atomic JSON write failed", {"path": str(path), "errno": exc.errno,
                              "error": str(exc), "replaced": committed}) from exc
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    @staticmethod
    def _kind(kind, write=False):
        if kind not in KINDS and not (kind == "facts" and not write):
            raise DomainError("UNKNOWN_KIND", f"Unsupported record collection: {kind}")

    def _record_path(self, kind, identifier):
        _string(identifier, "record_id")
        return self._path("records", kind, digest(identifier) + ".json")

    def _get_record(self, kind, identifier):
        value = self._read_json(self._record_path(kind, identifier))
        if not isinstance(value, dict) or set(value) != {"kind", "record_id", "record", "checksum"}:
            raise DomainError("CORRUPT_RECORD", "Invalid record envelope", {"kind": kind, "record_id": identifier})
        if (value["kind"] != kind or value["record_id"] != identifier
                or digest(value["record"]) != value["checksum"]):
            raise DomainError("CORRUPT_RECORD", "Stored record identity/checksum mismatch",
                              {"kind": kind, "record_id": identifier})
        return value["record"]

    def get(self, kind, record_id):
        self._kind(kind)
        return self._get_record(kind, record_id)

    def list(self, kind, project_id=None):
        self._kind(kind)
        directory = self._path("records", kind)
        if not directory.exists():
            return []
        records = []
        for path in sorted(directory.iterdir()):
            if path.suffix != ".json":
                continue
            envelope = self._read_json(path)
            if not isinstance(envelope, dict) or "record_id" not in envelope:
                raise DomainError("CORRUPT_RECORD", "Stored record lacks identity", {"path": str(path)})
            identifier = envelope["record_id"]
            if not isinstance(identifier, str) or path.name != digest(identifier) + ".json":
                raise DomainError("CORRUPT_RECORD", "Record filename does not match identity", {"path": str(path)})
            value = self._get_record(kind, identifier)
            if project_id is None or value.get("project_id") == project_id:
                records.append(value)
        return records

    def _put_unlocked(self, kind, identifier, record):
        path = self._record_path(kind, identifier)
        if path.exists() or path.is_symlink():
            existing = self._get_record(kind, identifier)
            if existing != record:
                raise DomainError("IMMUTABLE_CONFLICT", "Record ID already has different content",
                                  {"kind": kind, "record_id": identifier})
            return existing
        envelope = {"kind": kind, "record_id": identifier, "record": record, "checksum": digest(record)}
        self._atomic_write(path, envelope)
        return deepcopy(record)

    def put(self, kind, record_id, record):
        self._kind(kind, write=True)
        _string(record_id, "record_id")
        record = json.loads(json_bytes(record))
        if not isinstance(record, dict):
            raise DomainError("INVALID_ARGUMENT", "Records must be JSON objects")
        with self._write_lock():
            if kind in SCHEMA_KINDS:
                schema_name, identity_key = SCHEMA_KINDS[kind]
                record = validate(schema_name, record)
                if record.get(identity_key) != record_id:
                    raise DomainError("REFERENCE_MISMATCH", "Record key does not match its body",
                                      {"field": identity_key, "expected": record_id, "actual": record.get(identity_key)})
            if kind == "contexts":
                self._check_context(record_id, record)
            elif kind == "episodes":
                self._check_episode(record)
            elif kind == "feedback":
                self._check_feedback(record)
            elif kind == "assessments":
                self._check_assessment(record)
            return self._put_unlocked(kind, record_id, record)

    def remember(self, kind, content, source, project_id=None, memory_id=None, applicability=None):
        if kind not in {"user", "project"}:
            raise DomainError("INVALID_ARGUMENT", "Fact kind must be user or project")
        _string(content, "content")
        if not isinstance(source, (str, dict)) or not source:
            raise DomainError("INVALID_ARGUMENT", "Explicit fact source is required")
        if kind == "user" and project_id is not None:
            raise DomainError("INVALID_ARGUMENT", "User facts have global scope; omit project_id")
        if kind == "project":
            _string(project_id, "project_id")
        if applicability is not None:
            if (not isinstance(applicability, dict)
                    or set(applicability) - {"task_ids", "task_families", "query_terms", "global"}
                    or ("global" in applicability and type(applicability["global"]) is not bool)
                    or any(not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value)
                           for key, value in applicability.items() if key != "global")):
                raise DomainError("INVALID_ARGUMENT", "Invalid explicit fact applicability")
        with self._write_lock():
            previous = None
            if memory_id is not None:
                matches = [x for x in self.list("facts") if x["memory_id"] == memory_id]
                if not matches:
                    raise DomainError("NOT_FOUND", "Cannot correct an unknown fact", {"memory_id": memory_id})
                previous = max(matches, key=lambda x: x["revision"])
                _same_project(previous, project_id)
                if previous["kind"] != kind:
                    raise DomainError("REFERENCE_MISMATCH", "Fact correction cannot change kind")
            else:
                memory_id = new_id("memory")
            revision = 1 if previous is None else previous["revision"] + 1
            fact = {"memory_id": memory_id, "revision": revision, "record_id": f"{memory_id}:r{revision}",
                    "kind": kind, "project_id": project_id, "content": content, "source": source,
                    "supersedes": None if previous is None else previous["record_id"], "created_at": now_iso()}
            if applicability is not None or previous and "applicability" in previous:
                fact["applicability"] = deepcopy(applicability if applicability is not None else previous["applicability"])
            fact = json.loads(json_bytes(fact))
            return self._put_unlocked("facts", fact["record_id"], fact)

    def facts(self, project_id, legacy_root=None):
        _string(project_id, "project_id")
        latest = {}
        for fact in self.list("facts"):
            prior = latest.get(fact["memory_id"])
            if prior is None or fact["revision"] > prior["revision"]:
                latest[fact["memory_id"]] = fact
        result = {"user": [], "project": [], "errors": []}
        for fact in sorted(latest.values(), key=lambda x: x["memory_id"]):
            if fact["kind"] == "user" or fact["project_id"] == project_id:
                result[fact["kind"]].append(fact)
        if legacy_root is not None:
            self._legacy_facts(Path(os.path.abspath(legacy_root)), project_id, result)
        return result

    def _legacy_facts(self, root, project, result):
        try:
            self._no_symlinks(root)
        except DomainError as exc:
            result["errors"].append({"path": str(root), "code": exc.code, "message": exc.message})
            return
        for folder in ("people", "projects"):
            directory = root / folder
            if not directory.exists():
                continue
            try:
                self._no_symlinks(directory)
            except DomainError as exc:
                result["errors"].append({"path": str(directory), "code": exc.code, "message": exc.message})
                continue
            def walk_error(error):
                result["errors"].append({"path": str(error.filename), "code": "LEGACY_READ_ERROR", "message": str(error)})
            for current, dirs, files in os.walk(directory, followlinks=False, onerror=walk_error):
                for name in list(dirs):
                    path = Path(current) / name
                    if path.is_symlink():
                        dirs.remove(name)
                        result["errors"].append({"path": str(path), "code": "UNSAFE_PATH", "message": "Skipped symlink"})
                for name in sorted(files):
                    if not name.endswith(".md"):
                        continue
                    path = Path(current) / name
                    try:
                        self._no_symlinks(path)
                        markdown = path.read_text(encoding="utf-8")
                        match = re.match(r"^---\n([\s\S]*?)\n---\n\n([\s\S]*)$", markdown)
                        if not match:
                            raise ValueError("Expected JSON frontmatter followed by Markdown body")
                        item = json.loads(match.group(1))
                        if not isinstance(item, dict):
                            raise ValueError("Frontmatter must be an object")
                        if item.get("status") != "verified" or item.get("kind") not in {"personal", "project"}:
                            continue
                        if item["kind"] == "project" and item.get("scope") != project:
                            continue
                        claim = re.search(r"## Claim\n\n([\s\S]*?)(?=\n## Metadata\n|\s*$)", match.group(2))
                        content = claim.group(1).strip() if claim else item.get("content")
                        _string(content, "legacy.content")
                        kind = "user" if item["kind"] == "personal" else "project"
                        result[kind].append({"memory_id": item.get("id", str(path)), "kind": kind,
                                             "project_id": None if kind == "user" else project,
                                             "content": content, "source": item.get("source"),
                                             "legacy_path": str(path), "legacy_status": "verified"})
                    except (OSError, ValueError, DomainError) as exc:
                        result["errors"].append({"path": str(path), "code": getattr(exc, "code", "LEGACY_PARSE_ERROR"),
                                                 "message": str(exc)})

    def _check_context(self, identifier, record):
        if record.get("manifest_id") != identifier:
            raise DomainError("REFERENCE_MISMATCH", "Context manifest ID does not match record ID")
        project = _string(record.get("project_id"), "project_id")
        for field in ("task_ref", "task_revision"):
            if record.get(field) is not None:
                _string(record[field], field)
        snapshot = self.snapshot(record.get("snapshot_digest"))
        _same_project(snapshot, project)
        for selected in record.get("selected_skills", []):
            key = selected.get("skill_id")
            actual = snapshot["skills"].get(key)
            if actual is None or actual["revision"] != selected.get("revision"):
                raise DomainError("REFERENCE_MISMATCH", "Context references an absent Skill revision", {"skill_id": key})
        if "supplied_text" in record and record.get("supplied_hash") != digest(record["supplied_text"]):
            raise DomainError("REFERENCE_MISMATCH", "Context text and supplied hash differ")

    def _check_episode(self, record, pending_feedback=None):
        project = record["project_id"]
        resolve_episode_source(self, record)
        source = record["source_snapshot_ref"]
        if source is not None:
            _same_project(self.snapshot(source), project)
        if record["context_ref"] is not None:
            context = self.get("contexts", record["context_ref"])
            _same_project(context, project)
            if source is not None and source != context["snapshot_digest"]:
                raise DomainError("REFERENCE_MISMATCH", "Episode snapshot differs from its context")
            if (record["task"]["task_id"] is not None and context.get("task_ref") is not None
                    and record["task"]["task_id"] != context["task_ref"]):
                raise DomainError("REFERENCE_MISMATCH", "Episode task differs from its context")
            if (record["task"]["revision"] is not None and context.get("task_revision") is not None
                    and record["task"]["revision"] != context["task_revision"]):
                raise DomainError("REFERENCE_MISMATCH", "Episode task revision differs from its context")
        event_ids = [x["event_id"] for x in record["events"]]
        if len(set(event_ids)) != len(event_ids):
            raise DomainError("REFERENCE_MISMATCH", "Duplicate event IDs in episode")
        for event in record["events"]:
            parent_episode = event.get("parent_episode_id")
            parent_events = event_ids
            if parent_episode is not None and parent_episode != record["episode_id"]:
                try:
                    parent = self.get("episodes", parent_episode)
                except DomainError as exc:
                    if exc.code != 'NOT_FOUND':
                        raise
                    parent = None
                if parent is None:
                    parent_events = None
                else:
                    _same_project(parent, project)
                    parent_events = None if parent.get('trace_ref') else [x["event_id"] for x in parent["events"]]
            parent_event = event.get("parent_event_id")
            if parent_event is not None and parent_events is not None and parent_event not in parent_events:
                raise DomainError("REFERENCE_MISMATCH", "Parent event is absent from referenced episode")
        for ref in record["feedback_refs"]:
            feedback = (pending_feedback or {}).get(ref)
            if feedback is None:
                feedback = self.get("feedback", ref)
            _same_project(feedback, project)
            if feedback["subject_ref"] != record["episode_id"]:
                raise DomainError("REFERENCE_MISMATCH", "Feedback belongs to another episode")

    def add_episode(self, episode, feedback_records=()):
        episode = validate("EpisodeRecord", episode)
        pending = {}
        for item in feedback_records:
            item = validate("Feedback", item)
            identifier = item["check_id"]
            if identifier in pending and pending[identifier] != item:
                raise DomainError("IMMUTABLE_CONFLICT", "Duplicate feedback ID has different content")
            pending[identifier] = item
        with self._write_lock():
            self._check_episode(episode, pending)
            for item in pending.values():
                self._check_feedback(item, episode)
            batch = [("episodes", episode["episode_id"], episode),
                     *(("feedback", key, item) for key, item in pending.items())]
            # Preflight all identities before writing any item. Each write is atomic;
            # an interrupted multi-record import is safely completed by exact retry.
            for kind, identifier, item in batch:
                path = self._record_path(kind, identifier)
                if path.exists() or path.is_symlink():
                    if self._get_record(kind, identifier) != item:
                        raise DomainError("IMMUTABLE_CONFLICT", "Imported ID already has different content",
                                          {"kind": kind, "record_id": identifier})
            for kind, identifier, item in batch:
                self._put_unlocked(kind, identifier, item)
            return deepcopy(episode)

    def _check_feedback(self, feedback, episode=None):
        if feedback.get('feedback_plan_ref') is not None:
            from .feedback import check_planned_feedback
            return check_planned_feedback(self, self.get('feedback_plans', feedback['feedback_plan_ref']), feedback)
        if episode is None:
            episode = self.get("episodes", feedback["subject_ref"])
        return check_feedback_binding(self, feedback, episode)

    def _check_assessment(self, assessment):
        if assessment.get('feedback_plan_ref') is not None:
            from .feedback import verify_assessment
            verify_assessment(self, assessment)
            return
        # Historical records retain the original exact single-feedback rule.
        if assessment.get('aggregation_rule') != 'single_task_outcome' or len(assessment['criterion_feedback_ids']) != 1:
            raise DomainError('UNSUPPORTED_AGGREGATION', 'Current assessments link one task_outcome feedback.')
        episode = self.get('episodes', assessment['subject_ref'])
        _same_project(episode, assessment.get('project_id'))
        feedback = self.get('feedback', assessment['criterion_feedback_ids'][0])
        source = check_feedback_binding(self, feedback, episode)
        if feedback['criterion_id'] != 'task_outcome' or any(assessment[key] != feedback[key] for key in ('outcome', 'score')):
            raise DomainError('REFERENCE_MISMATCH', 'Assessment must preserve the linked task_outcome result.')
        if assessment.get('run_id') is not None and feedback.get('run_id') is not None and assessment['run_id'] != feedback['run_id']:
            raise DomainError('REFERENCE_MISMATCH', 'Assessment refers to another run.')
        if source['known'] and assessment.get('run_id') is not None and assessment['run_id'] != source['run_id']:
            raise DomainError('REFERENCE_MISMATCH', 'Assessment contradicts the known episode source run.')
        group = source['group']
        if group is not None and assessment['protocol_id'] != group['protocol_id']:
            raise DomainError('REFERENCE_MISMATCH', 'Assessment protocol differs from the known run plan.')

    def add_feedback(self, feedback):
        feedback = validate("Feedback", feedback)
        return self.put("feedback", feedback["check_id"], feedback)

    def feedback_for(self, episode_id):
        episode = self.get("episodes", episode_id)
        for identifier in episode["feedback_refs"]:
            self.get("feedback", identifier)
        return [x for x in self.list("feedback", episode["project_id"]) if x["subject_ref"] == episode_id]

    @staticmethod
    def _asset_path(value):
        if (not isinstance(value, str) or "\\" in value or "\x00" in value
                or value.startswith("/") or any(x in {"", ".", ".."} for x in value.split("/"))):
            raise DomainError("UNSAFE_PATH", "Unsafe Skill asset path", {"path": value})
        pieces = value.split("/")
        if len(pieces) < 3 or pieces[1] not in {"scripts", "references", "templates"}:
            raise DomainError("UNSAFE_PATH", "Assets must live under a Skill-owned allowed directory", {"path": value})
        return pieces[0]

    def _check_snapshot(self, payload):
        if not isinstance(payload, dict) or set(payload) != {"project_id", "parent", "skills", "assets"}:
            raise DomainError("INVALID_SNAPSHOT", "Snapshot payload has incorrect fields")
        project = _string(payload["project_id"], "project_id")
        skills, assets = payload["skills"], payload["assets"]
        if not isinstance(skills, dict) or not isinstance(assets, dict):
            raise DomainError("INVALID_SNAPSHOT", "Skills and assets must be objects")
        references = []
        for key, skill in skills.items():
            if not isinstance(skill, dict) or set(skill) != {"skill_id", "revision", "project_id", "content", "asset_refs"}:
                raise DomainError("INVALID_SNAPSHOT", "SkillRevision has incorrect fields", {"skill_id": key})
            if key != skill["skill_id"]:
                raise DomainError("REFERENCE_MISMATCH", "Skill key differs from Skill identity")
            _string(key, "skill_id")
            _string(skill["revision"], "revision")
            _same_project(skill, project)
            content = validate("SkillContent", skill["content"])
            for field in ("depends_on", "declared_conflicts"):
                refs = content[field]
                if len(refs) != len(set(refs)) or key in refs or any(ref not in skills for ref in refs):
                    raise DomainError("REFERENCE_MISMATCH", "Invalid Skill relationship", {"skill_id": key, "field": field})
            if (not isinstance(skill["asset_refs"], list) or any(not isinstance(ref, str) for ref in skill["asset_refs"])
                    or len(skill["asset_refs"]) != len(set(skill["asset_refs"]))):
                raise DomainError("ASSET_MISMATCH", "Asset references must be a unique list")
            for ref in skill["asset_refs"]:
                if self._asset_path(ref) != key:
                    raise DomainError("ASSET_MISMATCH", "Asset belongs to another Skill", {"path": ref})
                references.append(ref)
        for path, text in assets.items():
            self._asset_path(path)
            if not isinstance(text, str):
                raise DomainError("ASSET_MISMATCH", "Asset content must be text", {"path": path})
        if set(references) != set(assets):
            raise DomainError("ASSET_MISMATCH", "Snapshot asset inventory is incomplete",
                              {"missing": sorted(set(references) - set(assets)), "unowned": sorted(set(assets) - set(references))})
        closures = {}
        def visit(key, trail):
            if key in trail:
                raise DomainError("DEPENDENCY_CYCLE", "Skill dependency cycle", {"cycle": [*trail, key]})
            if key not in closures:
                found = {key}
                for dep in skills[key]["content"]["depends_on"]:
                    found.update(visit(dep, [*trail, key]))
                closures[key] = found
            return closures[key]
        for key in skills:
            closure = visit(key, [])
            for member in closure:
                if set(skills[member]["content"]["declared_conflicts"]) & closure:
                    raise DomainError("DEPENDENCY_CONFLICT", "A required dependency conflicts with its closure", {"skill_id": key})

    def _save_snapshot_unlocked(self, payload):
        self._check_snapshot(payload)
        if payload["parent"] is not None:
            _same_project(self.snapshot(payload["parent"]), payload["project_id"])
        identifier = digest(payload)
        value = {"snapshot_id": identifier, **payload}
        path = self._path("snapshots", identifier + ".json")
        if path.exists() or path.is_symlink():
            existing = self.snapshot(identifier)
            if existing != value:
                raise DomainError("IMMUTABLE_CONFLICT", "Snapshot identity conflict")
            return existing
        self._atomic_write(path, value)
        return deepcopy(value)

    def save_snapshot(self, project_id, skills, assets, parent=None):
        payload = json.loads(json_bytes({"project_id": project_id, "parent": parent, "skills": skills, "assets": assets}))
        with self._write_lock():
            return self._save_snapshot_unlocked(payload)

    def snapshot(self, snapshot_id):
        if not isinstance(snapshot_id, str) or re.fullmatch(r"[a-f0-9]{64}", snapshot_id) is None:
            raise DomainError("INVALID_ARGUMENT", "Snapshot identity must be a SHA256 digest")
        value = self._read_json(self._path("snapshots", snapshot_id + ".json"))
        if not isinstance(value, dict):
            raise DomainError("CORRUPT_SNAPSHOT", "Snapshot is not an object")
        payload = {k: v for k, v in value.items() if k != "snapshot_id"}
        if value.get("snapshot_id") != snapshot_id or digest(payload) != snapshot_id:
            raise DomainError("CORRUPT_SNAPSHOT", "Snapshot content does not match its digest")
        self._check_snapshot(payload)
        return value

    def _active_path(self, project_id):
        _string(project_id, "project_id")
        return self._path("projects", digest(project_id), "active.json")

    def _read_active(self, project_id):
        value = self._read_json(self._active_path(project_id))
        if not isinstance(value, dict) or value.get("project_id") != project_id:
            raise DomainError("CORRUPT_RECORD", "Active pointer project mismatch")
        _same_project(self.snapshot(value.get("snapshot_id")), project_id)
        if type(value.get("generation")) is not int or value["generation"] < 0:
            raise DomainError("CORRUPT_RECORD", "Invalid active generation")
        history = value.get("committed_release_ids")
        if (not isinstance(history, list) or any(not isinstance(ref, str) for ref in history)
                or len(history) != len(set(history)) or len(history) != value["generation"]):
            raise DomainError("CORRUPT_RECORD", "Active commit history does not match generation")
        if history:
            commit = self.get("releases", history[-1])
            if (value.get("release_id") != history[-1] or value.get("commit") != commit
                    or commit["new_digest"] != value["snapshot_id"] or commit["new_generation"] != value["generation"]):
                raise DomainError("CORRUPT_RECORD", "Active pointer and commit differ")
        elif (value.get("release_id") is not None or value.get("commit") is not None
              or value["snapshot_id"] != self._baseline_digest(project_id, value)):
            raise DomainError("CORRUPT_RECORD", "Bootstrap must match the immutable initial baseline")
        if value.get("baseline_ref") is not None:
            self._baseline_digest(project_id, value)
        return value

    def _baseline_digest(self, project_id, active):
        if active.get("baseline_ref") is None:
            return digest({"project_id": project_id, "parent": None, "skills": {}, "assets": {}})
        baseline = validate("BaselineRecord", self.get("baselines", active["baseline_ref"]))
        _same_project(baseline, project_id)
        snapshot = self.snapshot(baseline["snapshot_digest"])
        _same_project(snapshot, project_id)
        normalized = {"skills": {key: {k: v for k, v in value.items() if k != "project_id"}
                                  for key, value in snapshot["skills"].items()}, "assets": snapshot["assets"]}
        if (baseline["baseline_id"] != active["baseline_ref"] or snapshot["parent"] is not None
                or baseline["seed_content_hash"] != digest(normalized)
                or baseline["kind"] == "empty" and (snapshot["skills"] or snapshot["assets"])):
            raise DomainError("CORRUPT_RECORD", "Initial baseline identity/content mismatch")
        return snapshot["snapshot_id"]

    def initialize_project(self, project_id, *, seed=None, source=None):
        """Create an explicit generation-zero baseline; never replace an existing one."""
        _string(project_id, "project_id")
        if seed is not None and (not isinstance(seed, dict) or set(seed) != {"skills", "assets"} or not source):
            raise DomainError("INVALID_ARGUMENT", "A seed requires skills/assets and explicit provenance")
        value = deepcopy(seed) if seed is not None else {"skills": {}, "assets": {}}
        if not isinstance(value["skills"], dict):
            raise DomainError("INVALID_SNAPSHOT", "Seed Skills must be an object")
        for skill in value["skills"].values():
            if not isinstance(skill, dict):
                raise DomainError("INVALID_SNAPSHOT", "Seed Skill must be an object")
            skill["project_id"] = project_id
        payload = {"project_id": project_id, "parent": None, **value}
        self._check_snapshot(payload)
        normalized = {"skills": {key: {k: v for k, v in skill.items() if k != "project_id"}
                                  for key, skill in value["skills"].items()}, "assets": value["assets"]}
        with self._write_lock():
            path = self._active_path(project_id)
            if path.exists() or path.is_symlink():
                current = self._read_active(project_id)
                if self._baseline_digest(project_id, current) != digest(payload):
                    raise DomainError("BASELINE_CONFLICT", "Existing project baseline cannot be replaced")
                return current
            snapshot = self._save_snapshot_unlocked(payload)
            baseline_id = "baseline_" + digest([project_id, snapshot["snapshot_id"]])
            baseline = validate("BaselineRecord", {"baseline_id": baseline_id, "project_id": project_id,
                "kind": "seed" if seed is not None else "empty", "snapshot_digest": snapshot["snapshot_id"],
                "seed_content_hash": digest(normalized), "source": source if seed is not None else "explicit empty initialization",
                "created_at": now_iso()})
            baseline_path = self._record_path("baselines", baseline_id)
            if not baseline_path.exists():
                self._put_unlocked("baselines", baseline_id, baseline)
            pointer = {"project_id": project_id, "snapshot_id": snapshot["snapshot_id"], "generation": 0,
                "release_id": None, "commit": None, "committed_release_ids": [], "baseline_ref": baseline_id,
                "bootstrap": baseline["kind"] + "_unmeasured"}
            self._atomic_write(path, pointer)
            return deepcopy(pointer)

    def ensure_project(self, project_id):
        path = self._active_path(project_id)
        if path.exists() or path.is_symlink():
            return self._read_active(project_id)
        try:
            return self.initialize_project(project_id)
        except DomainError as exc:
            if exc.code != "BASELINE_CONFLICT":
                raise
            return self._read_active(project_id)

    def active(self, project_id):
        return self.ensure_project(project_id)

    def release_history(self, project_id):
        active = self.active(project_id)
        records = [self.get("releases", ref) for ref in active["committed_release_ids"]]
        prior = self._baseline_digest(project_id, active)
        for index, release in enumerate(records):
            _same_project(release, project_id)
            if (release["status"] != "published" or release["expected_active_digest"] != prior
                    or release["expected_generation"] != index or release["new_generation"] != index + 1):
                raise DomainError("CORRUPT_RECORD", "Committed release history is inconsistent")
            prior = release["new_digest"]
        return records

    def _commit_release(self, project_id, expected_snapshot_id, expected_generation, release_record):
        """N10-only byte/identity CAS after its policy/selection validation."""
        release = validate("ReleaseRecord", release_record)
        _same_project(release, project_id)
        if (release["status"] != "published" or release["expected_active_digest"] != expected_snapshot_id
                or release["expected_generation"] != expected_generation
                or release["new_generation"] != expected_generation + 1):
            raise DomainError("REFERENCE_MISMATCH", "Release does not match requested CAS")
        with self._write_lock():
            active = self._read_active(project_id)
            if release["release_id"] in active["committed_release_ids"]:
                existing = self.get("releases", release["release_id"])
                if existing != release:
                    raise DomainError("IMMUTABLE_CONFLICT", "Committed release differs")
                return existing
            if active["snapshot_id"] != expected_snapshot_id or active["generation"] != expected_generation:
                raise DomainError("STALE_BASE", "Active version/generation changed", {"active": active})
            candidate = self.snapshot(release["new_digest"])
            _same_project(candidate, project_id)
            self._put_unlocked("releases", release["release_id"], release)
            pointer = {"project_id": project_id, "snapshot_id": candidate["snapshot_id"],
                       "generation": expected_generation + 1, "release_id": release["release_id"],
                       "commit": release, "committed_release_ids": [*active["committed_release_ids"], release["release_id"]]}
            if "baseline_ref" in active:
                pointer["baseline_ref"] = active["baseline_ref"]
            self._atomic_write(self._active_path(project_id), pointer)
            return deepcopy(release)
