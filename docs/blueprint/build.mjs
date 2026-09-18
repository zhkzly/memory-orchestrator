import { readFileSync, writeFileSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";

const dir = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(dir, "../..");
const source = path.join(dir, "project-contract.json");
const template = path.join(dir, "viewer.template.html");
const htmlPath = path.join(dir, "index.html");
const contextPath = path.join(dir, "context.md");
const baselinePath = path.join(repo, "docs/history/2026-09-18-pre-blueprint/requirements-ledger.md.txt");
const operations = ["ADD", "PATCH", "RETIRE", "NOOP"];
const guards = ["validation.accepted", "base_matches", "assets_complete", "exact_candidate_matches", "config_protocol_match", "selection_matches"];
const questionBaseline = Array.from({ length: 28 }, (_, i) => "Q" + String(i + 1).padStart(2, "0"));
const responsibilityOwners = ["memory_system", "provided_function"];
const adjustmentStatuses = ["preserved", "boundary_changed", "parameter_unfixed", "deferred"];
const generatedPaths = new Set(["docs/blueprint/index.html", "docs/blueprint/context.md"]);
const sha = (text) => createHash("sha256").update(text).digest("hex");
const object = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
const responsibilityLabel = (value) => ({ memory_system: "记忆系统", provided_function: "调用方提供的函数" })[value] || value;

function validate(c, checkPaths = true) {
  const errors = [];
  const add = (code, field, message) => errors.push({ code, field, message });
  if (!c || c.schema_version !== 1) {
    add("E_SCHEMA", "schema_version", "Expected project contract schema_version=1.");
    return errors;
  }
  for (const field of ["requirements", "records", "nodes", "invariants", "edges", "operations", "authority", "questions", "schemas", "prompts", "examples", "paper_sources"]) {
    if (!Array.isArray(c[field]) || c[field].length === 0) add("E_EMPTY", field, "A non-empty array is required.");
  }
  if (errors.length) return errors;
  if (!/^\d+\.\d+\.\d+$/.test(c.meta?.version || "")) add("E_VERSION", "meta.version", "Use an explicit semantic version.");
  const ids = (field) => {
    const set = new Set();
    c[field].forEach((item, i) => {
      if (!item || typeof item.id !== "string" || !item.id) add("E_ID", field + "[" + i + "]", "Missing stable id.");
      else if (set.has(item.id)) add("E_DUP_ID", field + "." + item.id, "Duplicate id.");
      else set.add(item.id);
    });
    return set;
  };
  const nodeIds = ids("nodes"), recordIds = ids("records"), reqIds = ids("requirements"), invIds = ids("invariants");
  const opIds = ids("operations"), questionIds = ids("questions"), schemaIds = ids("schemas"), promptIds = ids("prompts"), paperIds = ids("paper_sources");
  ids("examples");
  const textRequired = (item, fields, prefix) => {
    for (const field of fields) if (typeof item?.[field] !== "string" || !item[field].trim()) add("E_FIELD", prefix + "." + field, "Non-empty text is required.");
  };
  const references = (values, known, field, code, nonempty = false) => {
    if (!Array.isArray(values) || (nonempty && !values.length)) { add(code, field, nonempty ? "A non-empty reference array is required." : "A reference array is required."); return; }
    for (const id of values) if (!known.has(id)) add(code, field, "Unknown reference: " + id);
  };
  const textList = (values, field, code, nonempty = true) => {
    if (!Array.isArray(values) || (nonempty && !values.length) || values.some((value) => typeof value !== "string" || !value.trim())) add(code, field, "An explicit array of non-empty text values is required.");
  };
  const baselineIds = [...readFileSync(baselinePath, "utf8").matchAll(/^\| (K\d{2}) \|/gm)].map((m) => m[1]);
  const retired = new Set((c.deprecations || []).filter((d) => d.id && d.reason && d.user_source && d.revision).map((d) => d.id));
  for (const id of baselineIds) if (!reqIds.has(id) && !retired.has(id)) add("E_MISSING_REQUIREMENT", "requirements." + id, "Retain the confirmed requirement or record an explicit sourced deprecation.");
  for (const id of questionBaseline) if (!questionIds.has(id) && !retired.has(id)) add("E_MISSING_QUESTION", "questions." + id, "Retain the reconstructed user question or record an explicit sourced deprecation.");
  for (const q of c.questions) {
    textRequired(q, ["title", "origin", "gap", "decision", "acceptance", "status"], q.id);
    references(q.requirement_ids, reqIds, q.id + ".requirement_ids", "E_REQUIREMENT_REF", true);
    references(q.node_ids, nodeIds, q.id + ".node_ids", "E_NODE_REF", true);
    references(q.paper_ids, paperIds, q.id + ".paper_ids", "E_PAPER_REF");
  }
  for (const requirement of c.requirements) {
    if (!Array.isArray(requirement.node_ids) || !requirement.node_ids.length) add("E_UNMAPPED_REQUIREMENT", requirement.id, "Map the requirement to at least one node.");
    for (const id of requirement.node_ids || []) if (!nodeIds.has(id)) add("E_NODE_REF", requirement.id, "Unknown node: " + id);
  }
  for (const n of c.nodes) {
    for (const field of ["inputs", "outputs", "writes", "preconditions", "postconditions", "requirements", "invariants"]) {
      if (!Array.isArray(n[field]) || !n[field].length) add("E_NODE_CONTRACT", n.id + "." + field, "Non-empty node contract field required.");
    }
    if (!n.operator || !n.on_unknown) add("E_NODE_CONTRACT", n.id, "Operator and unknown behavior are required.");
    if (!object(n.responsibility) || !responsibilityOwners.includes(n.responsibility.owner)) add("E_NODE_RESPONSIBILITY", n.id + ".responsibility.owner", "Use memory_system or provided_function; a provided operation is not a concrete client adapter.");
    textRequired(n.responsibility, ["description"], n.id + ".responsibility");
    for (const id of [...(n.inputs || []), ...(n.outputs || [])]) if (!recordIds.has(id)) add("E_TYPE_REF", n.id, "Unknown record type: " + id);
    for (const id of n.requirements || []) if (!reqIds.has(id)) add("E_REQUIREMENT_REF", n.id, "Unknown requirement: " + id);
    for (const id of n.invariants || []) if (!invIds.has(id)) add("E_INVARIANT_REF", n.id, "Unknown invariant: " + id);
    if (!["planned", "partial", "implemented"].includes(n.status)) add("E_STATUS", n.id, "Unknown implementation status.");
    if (n.status === "implemented" && (!Array.isArray(n.evidence_refs) || !n.evidence_refs.length)) add("E_IMPLEMENTATION_EVIDENCE", n.id, "An implemented claim requires evidence references.");
    const implementation = n.implementation;
    if (!implementation || typeof implementation !== "object" || Array.isArray(implementation)) add("E_NODE_IMPLEMENTATION", n.id + ".implementation", "An explicit implementation contract is required.");
    else {
      textRequired(implementation, ["owner", "signature", "state"], n.id + ".implementation");
      for (const field of ["steps", "checks", "errors"]) if (!Array.isArray(implementation[field]) || !implementation[field].length || implementation[field].some((value) => typeof value !== "string" || !value.trim())) add("E_NODE_IMPLEMENTATION", n.id + ".implementation." + field, "Non-empty implementation steps, checks and error behavior are required.");
      references(implementation.prompt_ids, promptIds, n.id + ".implementation.prompt_ids", "E_PROMPT_REF");
      references(implementation.paper_ids, paperIds, n.id + ".implementation.paper_ids", "E_PAPER_REF");
      if (implementation.schema_ids) references(implementation.schema_ids, schemaIds, n.id + ".implementation.schema_ids", "E_SCHEMA_REF");
      if (implementation.state === "implemented" && !n.evidence_refs?.length) add("E_IMPLEMENTATION_EVIDENCE", n.id + ".implementation.state", "An implemented claim requires evidence references.");
      for (const id of implementation.prompt_ids || []) {
        const prompt = c.prompts.find((p) => p.id === id);
        if (prompt && prompt.node_id !== n.id) add("E_PROMPT_MAPPING", n.id + ".implementation.prompt_ids", "Prompt belongs to a different node: " + id);
      }
    }
  }
  for (const schema of c.schemas) {
    textRequired(schema, ["title"], "schemas." + schema.id);
    if (!schema.json_schema || typeof schema.json_schema !== "object" || Array.isArray(schema.json_schema)) add("E_SCHEMA_DEFINITION", "schemas." + schema.id, "A JSON Schema object is required; this document checker does not execute JSON Schema validation.");
    if (schema.node_ids) references(schema.node_ids, nodeIds, "schemas." + schema.id + ".node_ids", "E_NODE_REF");
  }
  for (const prompt of c.prompts) {
    textRequired(prompt, ["node_id", "output_schema", "system", "user_template"], "prompts." + prompt.id);
    if (!nodeIds.has(prompt.node_id)) add("E_NODE_REF", "prompts." + prompt.id + ".node_id", "Unknown prompt node: " + prompt.node_id);
    if (!schemaIds.has(prompt.output_schema)) add("E_SCHEMA_REF", "prompts." + prompt.id + ".output_schema", "Unknown output schema: " + prompt.output_schema);
    for (const field of ["input_fields", "validation"]) if (!Array.isArray(prompt[field]) || !prompt[field].length) add("E_PROMPT_CONTRACT", "prompts." + prompt.id + "." + field, "Prompt inputs and validation rules must be explicit.");
    if (Array.isArray(prompt.input_fields) && typeof prompt.user_template === "string") {
      const fields = new Set(prompt.input_fields);
      const templateFields = new Set([...prompt.user_template.matchAll(/\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}/g)].map((match) => match[1]));
      if (fields.size !== prompt.input_fields.length || prompt.input_fields.some((field) => typeof field !== "string" || !field.trim()) || [...fields].some((field) => !templateFields.has(field)) || [...templateFields].some((field) => !fields.has(field))) add("E_PROMPT_FIELDS", "prompts." + prompt.id, "input_fields must match the user_template placeholders exactly, without duplicates or unused fields.");
    }
    if (!prompt.on_error || (Array.isArray(prompt.on_error) && !prompt.on_error.length)) add("E_PROMPT_CONTRACT", "prompts." + prompt.id + ".on_error", "Specify prompt failure behavior.");
    const node = c.nodes.find((n) => n.id === prompt.node_id);
    if (node && !node.implementation?.prompt_ids?.includes(prompt.id)) add("E_PROMPT_MAPPING", "prompts." + prompt.id, "The owning node must list this prompt in implementation.prompt_ids.");
  }
  for (const example of c.examples) {
    textRequired(example, ["title", "schema_id"], "examples." + example.id);
    if (!schemaIds.has(example.schema_id)) add("E_SCHEMA_REF", "examples." + example.id + ".schema_id", "Unknown example schema: " + example.schema_id);
    if (!Object.hasOwn(example, "value")) add("E_EXAMPLE", "examples." + example.id + ".value", "An example payload is required.");
    if (example.kind !== "illustrative_not_measured") add("E_EXAMPLE", "examples." + example.id + ".kind", "Design examples must be explicitly illustrative_not_measured.");
  }
  for (const paper of c.paper_sources) {
    textRequired(paper, ["title", "url", "mechanism", "limitation", "evidence_level"], "paper_sources." + paper.id);
    for (const url of [paper.url, ...(Array.isArray(paper.code_urls) ? paper.code_urls : [])]) if (typeof url !== "string" || !/^https?:\/\//.test(url)) add("E_PAPER_URL", "paper_sources." + paper.id, "Use an explicit HTTP(S) primary-source URL.");
    if (!Array.isArray(paper.code_urls)) add("E_PAPER_URL", "paper_sources." + paper.id + ".code_urls", "Code URLs must be an array, possibly empty.");
  }
  const runtime = c.runtime;
  if (!runtime || typeof runtime !== "object" || Array.isArray(runtime)) add("E_RUNTIME", "runtime", "Execution and evaluation design is required.");
  else {
    textRequired(runtime, ["status", "topology", "first_backend"], "runtime");
    const delivery = runtime.current_delivery;
    if (!object(delivery)) add("E_CURRENT_DELIVERY", "runtime.current_delivery", "Current scope and permission must be explicit and visible in generated views.");
    else {
      textRequired(delivery, ["scope", "source"], "runtime.current_delivery");
      for (const field of ["in", "out", "dependencies"]) textList(delivery[field], "runtime.current_delivery." + field, "E_CURRENT_DELIVERY", field !== "dependencies");
      if (typeof delivery.implementation_allowed !== "boolean") add("E_IMPLEMENTATION_PERMISSION", "runtime.current_delivery.implementation_allowed", "Declare implementation permission explicitly as a boolean for the current scope.");
    }
    if (!Array.isArray(runtime.adjustments) || !runtime.adjustments.length) add("E_ADJUSTMENTS", "runtime.adjustments", "Record preserved capabilities and explicit boundary or parameter changes.");
    else {
      const adjustmentIds = new Set();
      for (const adjustment of runtime.adjustments) {
        const prefix = "runtime.adjustments." + (adjustment?.id || "?");
        textRequired(adjustment, ["id", "area", "before", "after", "reason", "status"], prefix);
        if (adjustmentIds.has(adjustment?.id)) add("E_DUP_ID", prefix, "Duplicate adjustment id.");
        adjustmentIds.add(adjustment?.id);
        if (!adjustmentStatuses.includes(adjustment?.status)) add("E_ADJUSTMENTS", prefix + ".status", "Use preserved, boundary_changed, parameter_unfixed, or deferred.");
        for (const [field, known, code] of [["node_ids", nodeIds, "E_NODE_REF"], ["requirement_ids", reqIds, "E_REQUIREMENT_REF"], ["question_ids", questionIds, "E_QUESTION_REF"]]) if (adjustment?.[field] !== undefined) references(adjustment[field], known, prefix + "." + field, code);
      }
    }
    const evaluation = runtime.evaluation_policy;
    if (!object(evaluation)) add("E_EVALUATION_POLICY", "runtime.evaluation_policy", "Separate fixed rules, unselected protocol parameters, and historical examples.");
    else {
      textList(evaluation.fixed_rules, "runtime.evaluation_policy.fixed_rules", "E_EVALUATION_POLICY");
      for (const [field, required] of [["parameters", ["name", "status", "rule"]], ["historical_examples", ["name", "old_reference", "unconfirmed_draft", "decision"]]]) {
        if (!Array.isArray(evaluation[field])) add("E_EVALUATION_POLICY", "runtime.evaluation_policy." + field, "An explicit array is required.");
        else evaluation[field].forEach((item, i) => textRequired(item, required, "runtime.evaluation_policy." + field + "[" + i + "]"));
      }
    }
    for (const field of ["loop", "parallelism", "feedback", "metrics", "split_policy", "release_gate", "non_claims", "semantic_checks"]) if (!Array.isArray(runtime[field]) || !runtime[field].length) add("E_RUNTIME", "runtime." + field, "A non-empty runtime policy list is required.");
    for (const field of ["reference_profile", "model_client"]) if (!runtime[field] || typeof runtime[field] !== "object" || Array.isArray(runtime[field])) add("E_RUNTIME", "runtime." + field, "An explicit configuration object is required.");
    if (!runtime.worked_example || runtime.worked_example.kind !== "illustrative_not_measured" || !runtime.worked_example.title || !Array.isArray(runtime.worked_example.steps) || !runtime.worked_example.steps.length) add("E_RUNTIME", "runtime.worked_example", "An explicitly illustrative end-to-end example is required.");
  }
  for (const r of c.requirements) for (const id of r.node_ids || []) {
    const n = c.nodes.find((v) => v.id === id);
    if (n && !n.requirements?.includes(r.id)) add("E_COVERAGE_MISMATCH", r.id, "Node mapping must be reciprocal: " + id);
  }
  for (const n of c.nodes) for (const id of n.requirements || []) {
    const r = c.requirements.find((v) => v.id === id);
    if (r && !r.node_ids?.includes(n.id)) add("E_COVERAGE_MISMATCH", n.id, "Requirement mapping must be reciprocal: " + id);
  }
  for (const edge of c.edges) {
    const from = c.nodes.find((n) => n.id === edge.from), to = c.nodes.find((n) => n.id === edge.to);
    if (!from || !to) add("E_EDGE_REF", "edges", "Unknown endpoint.");
    else if (!from.outputs?.includes(edge.record) || !to.inputs?.includes(edge.record)) add("E_EDGE_TYPE", edge.from + "→" + edge.to, "Record must be an output and an input: " + edge.record);
  }
  const writers = c.nodes.filter((n) => n.writes?.includes("active_pointer")).map((n) => n.id);
  if (writers.length !== 1 || writers[0] !== c.policies?.active_writer) add("E_ACTIVE_OWNER", "nodes.writes", "Exactly the designated publisher may write active_pointer.");
  if (operations.some((o) => !opIds.has(o)) || [...opIds].some((o) => !operations.includes(o))) add("E_OPERATIONS", "operations", "Schema v1 operations are ADD/PATCH/RETIRE/NOOP.");
  if (JSON.stringify([...(c.policies?.allowed_operations || [])].sort()) !== JSON.stringify([...operations].sort())) add("E_OPERATIONS", "policies.allowed_operations", "Policy and operation definitions must agree.");
  if (guards.some((g) => !c.policies?.publication_guards?.includes(g))) add("E_PUBLICATION_GUARD", "policies.publication_guards", "Required publication conditions are missing.");
  const states = new Set(c.lifecycle?.states || []);
  if (!Array.isArray(c.lifecycle?.transitions) || !c.lifecycle.transitions.length) add("E_LIFECYCLE", "lifecycle", "Transitions are required.");
  for (const t of c.lifecycle?.transitions || []) {
    if (!states.has(t.from) || !states.has(t.to)) add("E_STATE_REF", "lifecycle", "Unknown state.");
    if (t.to !== "active") continue;
    if (t.owner !== c.policies?.active_writer || !["validated", "archived"].includes(t.from)) add("E_ACTIVE_TRANSITION", t.from + "→active", "Activation must be a publisher-controlled promotion or explicit rollback.");
    const required = t.from === "archived" ? ["explicit_rollback", "assets_complete", "compatible"] : guards;
    if (required.some((g) => !t.guards?.includes(g))) add("E_PUBLICATION_GUARD", t.from + "→active", "Activation guard list is incomplete.");
  }
  const reaches = (start, finish, excluded) => {
    const pending = [start], seen = new Set();
    while (pending.length) {
      const id = pending.pop();
      if (id === excluded || seen.has(id)) continue;
      if (id === finish) return true;
      seen.add(id);
      for (const e of c.edges) if (e.from === id) pending.push(e.to);
    }
    return false;
  };
  if (!reaches("N08", "N10")) add("E_RELEASE_PATH", "edges", "Candidate-to-publisher path is missing.");
  if (reaches("N08", "N10", "N09")) add("E_GATE_BYPASS", "edges", "Candidate-to-publisher paths must pass the validation node.");
  if (checkPaths) {
    for (const item of [...c.authority, ...(c.references || [])]) {
      if (generatedPaths.has(item.path)) continue;
      if (!existsSync(path.join(repo, item.path))) add("E_FILE_REF", item.path, "Referenced project file does not exist.");
    }
    for (const n of c.nodes) for (const ref of n.evidence_refs || []) {
      if (!/^[a-z]+:/.test(ref) && !existsSync(path.join(repo, ref))) add("E_FILE_REF", n.id, "Missing implementation evidence: " + ref);
    }
  }
  return errors;
}

function contextMarkdown(c, digest) {
  const delivery = c.runtime.current_delivery;
  const evaluation = c.runtime.evaluation_policy;
  const lines = [
    "# 项目总纲：执行入口", "",
    "自动生成，勿独立编辑。版本 " + c.meta.version + "；源 SHA-256：" + digest + "。", "",
    "目标：" + c.meta.purpose, "",
    "目标契约与实现证据分别列出；节点实现标注不代表学习收益。当前工作许可见下方本轮范围。", "",
    "权威源：docs/blueprint/project-contract.json；阅读视图：docs/blueprint/index.html。", "",
    "## 本轮范围与工作许可", "",
    delivery.scope, "",
    "**" + (delivery.implementation_allowed ? "产品实现已获授权" : "产品实现暂停") + "：implementation_allowed=" + delivery.implementation_allowed + "。是否已完成以节点证据为准。**", "",
    "本轮保留：", ...delivery.in.map((item) => "- " + item), "",
    "暂缓／不做：", ...delivery.out.map((item) => "- " + item), "",
    "需要调用方提供：", ...delivery.dependencies.map((item) => "- " + item), "",
    "范围来源：" + delivery.source, "",
    "逐项保留 " + c.questions.length + " 个用户问题（按对话重述编号，不冒充原始编号清单）；" + c.prompts.length + " 个提示词契约与 " + c.schemas.length + " 个结构定义。当前均须区分设计与实现证据。", "",
    "阅读路线：HTML 的“逐项问题”核对遗漏 → “执行与评价”明确并行、反馈与发布 → “节点契约”按需展开提示词、schema 和说明性示例。", "",
    "## 节点目录", "", "| ID | 节点 | 职责归属 | 契约 |", "| --- | --- | --- | --- |"
  ];
  for (const n of c.nodes) lines.push("| " + n.id + " | " + n.name + " | " + responsibilityLabel(n.responsibility.owner) + " | " + n.operator.replaceAll("|", "\\|") + " |");
  lines.push("", "职责详情见节点 responsibility；provided_function 是调用方提供的操作，与具体客户端适配分开。", "", "## 评价规则与待定参数", "");
  for (const rule of evaluation.fixed_rules) lines.push("- " + rule);
  for (const parameter of evaluation.parameters) lines.push("- 参数 " + parameter.name + "（" + parameter.status + "）：" + parameter.rule);
  lines.push("", "历史数值仅供追溯，不自动成为默认值；详见 runtime.evaluation_policy.historical_examples。", "");
  lines.push("", "## 固定边界", "");
  for (const i of c.invariants) lines.push("- " + i.id + " " + i.rule);
  lines.push("", "## 中断后恢复", "");
  for (const step of c.continuity.read_order) lines.push("- " + step);
  lines.push("", "按需读取节点：node docs/blueprint/build.mjs node N08。默认读取步骤、提示词和结构索引；确需完整 schema/示例时追加 --full。只加载当前节点和相关代码，不默认重读全部文献。", "", "用户的新要求可以修订总纲；先记录影响的节点与版本，不能用旧总纲拒绝明确的新方向。", "");
  return lines.join("\n");
}

function nodeBundle(c, n, full = false) {
  const types = new Set([...n.inputs, ...n.outputs]);
  const questions = c.questions.filter((q) => q.node_ids.includes(n.id));
  const prompts = c.prompts.filter((p) => n.implementation.prompt_ids.includes(p.id));
  const schemaIds = new Set([...types, ...(n.implementation.schema_ids || []), ...prompts.map((p) => p.output_schema)]);
  const schemas = c.schemas.filter((s) => schemaIds.has(s.id) || s.node_ids?.includes(n.id));
  const includedSchemas = new Set(schemas.map((s) => s.id));
  const paperIds = new Set([...n.implementation.paper_ids, ...questions.flatMap((q) => q.paper_ids)]);
  const runtimeFields = {
    N01: ["split_policy"], N02: [], N03: ["first_backend", "parallelism"],
    N04: [], N05: ["feedback"], N06: [], N07: [], N08: [],
    N09: ["parallelism", "split_policy", "release_gate"], N10: ["release_gate"], N11: ["metrics"]
  };
  const profileFields = {
    N01: [], N02: ["max_selected_roots", "skill_context_token_budget", "max_active_skills"],
    N03: ["learning_attempts", "max_parallel_runs", "cross_task_batch_size", "budget_rule"],
    N04: ["extract_input_tokens", "max_evidence_expansions"],
    N05: ["format_repair_attempts", "transport_retry_default"],
    N06: ["extract_input_tokens", "extract_output_tokens", "extract_cumulative_input_tokens", "max_evidence_expansions", "max_experiences_per_packet", "max_related_experiences", "format_repair_attempts", "transport_retry_default"],
    N07: ["max_related_experiences", "format_repair_attempts", "transport_retry_default"],
    N08: ["candidates_per_cycle", "max_active_skills", "format_repair_attempts", "transport_retry_default"],
    N09: ["validation_repeats", "max_parallel_runs", "candidates_per_cycle", "budget_rule"],
    N10: [], N11: ["budget_rule"]
  };
  const runtime = { status: c.runtime.status, topology: c.runtime.topology, current_delivery: c.runtime.current_delivery, evaluation_policy: c.runtime.evaluation_policy };
  if (full) runtime.adjustments = c.runtime.adjustments;
  if (c.runtime.design_discipline) runtime.design_discipline = c.runtime.design_discipline;
  for (const key of runtimeFields[n.id] || []) runtime[key] = c.runtime[key];
  const profileKeys = profileFields[n.id] || [];
  if (profileKeys.length) runtime.reference_profile = Object.fromEntries(["label", "normative", ...profileKeys].filter((key) => Object.hasOwn(c.runtime.reference_profile, key)).map((key) => [key, c.runtime.reference_profile[key]]));
  if (prompts.length) runtime.model_client = c.runtime.model_client;
  return {
    node: n, questions: full ? questions : questions.map(({ id, title }) => ({ id, title })),
    records: c.records.filter((r) => types.has(r.id)),
    requirements: c.requirements.filter((r) => n.requirements.includes(r.id)),
    invariants: c.invariants.filter((i) => n.invariants.includes(i.id)),
    prompts,
    schemas: full ? schemas : schemas.map(({ id, title }) => ({ id, title, source: "docs/blueprint/project-contract.json#/schemas/" + c.schemas.findIndex((s) => s.id === id) })),
    examples: c.examples.filter((e) => includedSchemas.has(e.schema_id)).map((e) => full ? e : ({ id: e.id, title: e.title, schema_id: e.schema_id, kind: e.kind })),
    paper_sources: c.paper_sources.filter((p) => paperIds.has(p.id)).map((p) => full ? p : ({ id: p.id, title: p.title, url: p.url, code_urls: p.code_urls })), runtime,
    detail_mode: full ? "full" : "compact; use node " + n.id + " --full for complete schema/example payloads"
  };
}

function render(c, raw) {
  const digest = sha(raw);
  const json = JSON.stringify(c).replaceAll("<", "\\u003c");
  const title = escapeHtml(c.meta.title);
  const delivery = c.runtime.current_delivery;
  const items = (values) => "<ul>" + values.map((value) => "<li>" + escapeHtml(value) + "</li>").join("") + "</ul>";
  const deliveryNotice = '<strong>本轮范围</strong><p>' + escapeHtml(delivery.scope) + '</p><p class="warning">' + (delivery.implementation_allowed ? '产品实现已获授权' : '产品实现暂停') + ' · implementation_allowed=' + escapeHtml(delivery.implementation_allowed) + '</p><details><summary>保留能力、暂缓事项与调用方职责</summary><h3>本轮保留</h3>' + items(delivery.in) + '<h3>暂缓／不做</h3>' + items(delivery.out) + '<h3>需要调用方提供</h3>' + items(delivery.dependencies) + '<p class="small">范围来源：' + escapeHtml(delivery.source) + '</p></details>';
  const html = readFileSync(template, "utf8").replaceAll("__PROJECT_TITLE__", () => title).replaceAll("__SOURCE_HASH__", () => digest).replaceAll("__CURRENT_DELIVERY_NOTICE__", () => deliveryNotice).replace("__CONTRACT_DATA__", () => json);
  return { html, context: contextMarkdown(c, digest), digest };
}

function selfTest(c) {
  const cases = [
    ["missing requirement", "E_MISSING_REQUIREMENT", (d) => { d.requirements = d.requirements.filter((r) => r.id !== "K10"); }],
    ["duplicate node", "E_DUP_ID", (d) => { d.nodes.push(structuredClone(d.nodes[0])); }],
    ["unknown record", "E_TYPE_REF", (d) => { d.nodes[0].inputs.push("ImaginaryRecord"); }],
    ["unauthorized active writer", "E_ACTIVE_OWNER", (d) => { d.nodes.find((n) => n.id === "N08").writes.push("active_pointer"); }],
    ["validation bypass", "E_GATE_BYPASS", (d) => { d.edges.push({ from: "N08", to: "N10", record: "PatchCandidate" }); }],
    ["missing publication guard", "E_PUBLICATION_GUARD", (d) => { d.lifecycle.transitions.find((t) => t.from === "validated" && t.to === "active").guards = ["validation.accepted"]; }],
    ["candidate directly active", "E_ACTIVE_TRANSITION", (d) => { d.lifecycle.transitions.push({ from: "candidate", to: "active", owner: "N10", guards }); }],
    ["unknown operation", "E_OPERATIONS", (d) => { d.operations.push({ id: "REWRITE_EVERYTHING", rule: "bad fixture" }); }],
    ["unsupported completion claim", "E_IMPLEMENTATION_EVIDENCE", (d) => { d.nodes[0].status = "implemented"; delete d.nodes[0].evidence_refs; }],
    ["empty node data", "E_EMPTY", (d) => { d.nodes = []; }],
    ["missing user question", "E_MISSING_QUESTION", (d) => { d.questions = d.questions.filter((q) => q.id !== "Q17"); }],
    ["missing node implementation", "E_NODE_IMPLEMENTATION", (d) => { delete d.nodes[0].implementation; }],
    ["unknown implementation prompt", "E_PROMPT_REF", (d) => { d.nodes[0].implementation.prompt_ids.push("missing_prompt"); }],
    ["prompt assigned to wrong node", "E_PROMPT_MAPPING", (d) => { const p = d.prompts[0]; p.node_id = d.nodes.find((n) => n.id !== p.node_id).id; }],
    ["unknown prompt schema", "E_SCHEMA_REF", (d) => { d.prompts[0].output_schema = "MissingOutput"; }],
    ["unknown node schema", "E_SCHEMA_REF", (d) => { d.nodes[0].implementation.schema_ids = ["MissingInput"]; }],
    ["unknown example schema", "E_SCHEMA_REF", (d) => { d.examples[0].schema_id = "MissingExample"; }],
    ["unknown source reference", "E_PAPER_REF", (d) => { d.questions[0].paper_ids.push("missing_paper"); }],
    ["missing exact candidate publication guard", "E_PUBLICATION_GUARD", (d) => { d.lifecycle.transitions.find((t) => t.from === "validated" && t.to === "active").guards = guards.filter((g) => g !== "exact_candidate_matches"); }],
    ["missing configuration publication guard", "E_PUBLICATION_GUARD", (d) => { d.policies.publication_guards = guards.filter((g) => g !== "config_protocol_match"); }],
    ["missing selection publication guard", "E_PUBLICATION_GUARD", (d) => { d.policies.publication_guards = guards.filter((g) => g !== "selection_matches"); }],
    ["missing selection activation guard", "E_PUBLICATION_GUARD", (d) => { d.lifecycle.transitions.find((t) => t.from === "validated" && t.to === "active").guards = guards.filter((g) => g !== "selection_matches"); }],
    ["missing current scope", "E_CURRENT_DELIVERY", (d) => { delete d.runtime.current_delivery; }],
    ["invalid implementation permission type", "E_IMPLEMENTATION_PERMISSION", (d) => { d.runtime.current_delivery.implementation_allowed = "true"; }],
    ["missing implementation permission", "E_IMPLEMENTATION_PERMISSION", (d) => { delete d.runtime.current_delivery.implementation_allowed; }],
    ["missing scope dependencies", "E_CURRENT_DELIVERY", (d) => { delete d.runtime.current_delivery.dependencies; }],
    ["concrete adapter confused with responsibility", "E_NODE_RESPONSIBILITY", (d) => { d.nodes[0].responsibility.owner = "codex_adapter"; }],
    ["missing node responsibility", "E_NODE_RESPONSIBILITY", (d) => { delete d.nodes[0].responsibility; }],
    ["missing evaluation policy", "E_EVALUATION_POLICY", (d) => { delete d.runtime.evaluation_policy; }],
    ["unknown adjustment status", "E_ADJUSTMENTS", (d) => { d.runtime.adjustments[0].status = "silently_removed"; }],
    ["unknown adjustment node", "E_NODE_REF", (d) => { d.runtime.adjustments[0].node_ids = ["N99"]; }],
    ["undeclared prompt field", "E_PROMPT_FIELDS", (d) => { d.prompts[0].user_template += " {{undisclosed_input}}"; }],
    ["unused prompt field", "E_PROMPT_FIELDS", (d) => { d.prompts[0].input_fields.push("unrendered_input"); }]
  ];
  const baseline = validate(c);
  if (baseline.length) return { ok: false, baseline };
  const results = cases.map(([name, expected, mutate]) => {
    const changed = structuredClone(c); mutate(changed);
    const errors = validate(changed, false);
    return { name, expected, caught: errors.some((e) => e.code === expected) };
  });
  const delivery = c.runtime.current_delivery;
  const markdown = contextMarkdown(c, "test-source-hash");
  const rendered = render(c, JSON.stringify(c));
  const withoutReferenceNumbers = structuredClone(c);
  withoutReferenceNumbers.runtime.reference_profile = { label: c.runtime.reference_profile.label, normative: false };
  const views = [
    { name: "context includes current scope and actual permission", passed: markdown.includes(delivery.scope) && markdown.includes("implementation_allowed=" + delivery.implementation_allowed) },
    { name: "HTML overview and runtime both include visible current scope", passed: ["overview-delivery", "runtime-delivery"].every((id) => rendered.html.includes('id="' + id + '"><strong>本轮范围</strong><p>' + escapeHtml(delivery.scope))) && !rendered.html.includes("__CURRENT_DELIVERY_NOTICE__") },
    { name: "both authorized and paused scopes validate and render truthfully", passed: [true, false].every((allowed) => {
      const changed = structuredClone(c); changed.runtime.current_delivery.implementation_allowed = allowed;
      const view = render(changed, JSON.stringify(changed));
      const label = allowed ? "产品实现已获授权" : "产品实现暂停";
      return validate(changed, false).length === 0 && view.context.includes(label + "：implementation_allowed=" + allowed) && view.html.includes(label + " · implementation_allowed=" + allowed);
    }) },
    { name: "every compact node includes current scope and evaluation policy", passed: c.nodes.every((n) => {
      const bundle = nodeBundle(c, n);
      return JSON.stringify(bundle.runtime.current_delivery) === JSON.stringify(delivery) && JSON.stringify(bundle.runtime.evaluation_policy) === JSON.stringify(c.runtime.evaluation_policy);
    }) },
    { name: "historical numeric examples are not mandatory defaults", passed: validate(withoutReferenceNumbers, false).length === 0 },
    { name: "compact node preserves reference configuration authority marker", passed: c.nodes.every((n) => {
      const profile = nodeBundle(c, n).runtime.reference_profile;
      return !profile || !Object.hasOwn(c.runtime.reference_profile, "normative") || profile.normative === c.runtime.reference_profile.normative;
    }) }
  ];
  return { ok: results.every((r) => r.caught) && views.every((v) => v.passed), baseline: "pass", derived_negative_cases: results, generated_view_checks: views };
}

function main() {
  const [command = "render", argument] = process.argv.slice(2);
  const input = command === "check" && argument ? path.resolve(argument) : source;
  const raw = readFileSync(input, "utf8"), c = JSON.parse(raw);
  const errors = validate(c);
  if (errors.length) { console.log(JSON.stringify({ ok: false, errors }, null, 2)); process.exitCode = 1; return; }
  if (command === "check") {
    console.log(JSON.stringify({ ok: true, contract_version: c.meta.version, questions: c.questions.length, requirements: c.requirements.length, nodes: c.nodes.length, records: c.records.length, invariants: c.invariants.length, prompts: c.prompts.length, schemas: c.schemas.length, examples: c.examples.length, paper_sources: c.paper_sources.length, scope: "Document structure and references only; JSON Schema payload validity, runtime behavior and learning quality require separate checks." }, null, 2));
  } else if (command === "node") {
    const n = c.nodes.find((v) => v.id === argument);
    if (!n) throw new Error("E_NODE_ID: unknown node " + argument);
    console.log(JSON.stringify({ contract_version: c.meta.version, source_sha256: sha(raw), ...nodeBundle(c, n, process.argv.slice(4).includes("--full")) }, null, 2));
  } else if (command === "self-test") {
    const result = selfTest(c); console.log(JSON.stringify(result, null, 2)); if (!result.ok) process.exitCode = 1;
  } else if (command === "render" || command === "verify") {
    const rendered = render(c, raw);
    if (command === "render") {
      writeFileSync(htmlPath, rendered.html); writeFileSync(contextPath, rendered.context);
    } else if (!existsSync(htmlPath) || !existsSync(contextPath) || readFileSync(htmlPath, "utf8") !== rendered.html || readFileSync(contextPath, "utf8") !== rendered.context) {
      console.log(JSON.stringify({ ok: false, code: "E_STALE_VIEW", message: "Generated views differ. Run node docs/blueprint/build.mjs render." }, null, 2)); process.exitCode = 1; return;
    }
    console.log(JSON.stringify({ ok: true, command, contract_version: c.meta.version, source_sha256: rendered.digest, html_bytes: Buffer.byteLength(rendered.html), context_bytes: Buffer.byteLength(rendered.context), outputs: ["docs/blueprint/index.html", "docs/blueprint/context.md"] }, null, 2));
  } else throw new Error("E_COMMAND: use check, render, verify, node <Nxx>, or self-test");
}

try { main(); } catch (error) { console.error(error.message); process.exitCode = 1; }
