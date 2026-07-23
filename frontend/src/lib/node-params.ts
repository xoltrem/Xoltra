/**
 * node-params.ts — declarative param schemas for the node config panel.
 *
 * Each entry mirrors exactly what the node's execute() function reads in
 * backend/node_library.py (`params.get(...)`) — field names here MUST match
 * those keys or the engine silently ignores the value. When adding a node
 * type to the backend, add its schema here.
 *
 * Unknown node types fall back to a raw JSON editor in the panel, so nothing
 * is ever un-configurable.
 */

export type ParamFieldType =
  | 'text'
  | 'textarea'
  | 'number'
  | 'select'
  | 'password'
  | 'json';

export interface ParamField {
  /** Key inside node.data.params — must match backend params.get(key). */
  key: string;
  label: string;
  type: ParamFieldType;
  placeholder?: string;
  help?: string;
  required?: boolean;
  options?: { value: string; label: string }[]; // for select
  min?: number;
  max?: number;
  step?: number;
}

export const PARAM_SCHEMAS: Record<string, ParamField[]> = {
  // ─── Triggers ──────────────────────────────────────────────────────────────
  'trigger.schedule': [
    {
      key: 'cron', label: 'Cron expression', type: 'text',
      placeholder: '0 9 * * 1-5',
      help: 'Standard 5-field cron. Scheduling is handled by the engine.',
      required: true,
    },
  ],
  'trigger.webhook': [], // webhook body arrives as trigger_data — nothing to configure
  'trigger.manual': [],

  // ─── AI ────────────────────────────────────────────────────────────────────
  'ai.cohere_generate': [
    {
      key: 'role', label: 'LLM role', type: 'select',
      options: [
        { value: 'architect', label: 'Architect (default)' },
        { value: 'critic', label: 'Critic' },
        { value: 'operator', label: 'Operator' },
        { value: 'qa', label: 'QA' },
      ],
      help: 'Which llm.py role profile handles the call.',
    },
    {
      key: 'preamble', label: 'Preamble', type: 'textarea',
      placeholder: 'Optional system-style instructions prepended to the prompt…',
    },
    {
      key: 'retries', label: 'Retries', type: 'number', min: 0, max: 5, step: 1,
      placeholder: '2',
    },
  ],
  'ai.web_search': [
    {
      key: 'query', label: 'Query', type: 'text',
      placeholder: 'latest AI automation trends',
      help: 'Used when no upstream node provides a query input.',
    },
    { key: 'num_results', label: 'Results', type: 'number', min: 1, max: 10, step: 1, placeholder: '5' },
    {
      key: 'role', label: 'Summarizer role', type: 'select',
      options: [
        { value: 'architect', label: 'Architect (default)' },
        { value: 'critic', label: 'Critic' },
        { value: 'qa', label: 'QA' },
      ],
    },
  ],
  'ai.cohere_embed': [], // text comes from the upstream input port

  // ─── Logic ─────────────────────────────────────────────────────────────────
  'logic.condition': [
    {
      key: 'expression', label: 'Expression', type: 'text',
      placeholder: "status == 'active'",
      help: 'Safe expression over the node inputs, e.g. value > 10. Routes to the true/false branch.',
      required: true,
    },
  ],
  'logic.loop': [], // iterates the upstream items input
  'logic.merge': [
    {
      key: 'strategy', label: 'Merge strategy', type: 'select',
      options: [
        { value: 'combine', label: 'Combine into one object' },
        { value: 'array', label: 'Collect into an array' },
      ],
    },
  ],

  // ─── Integrations ──────────────────────────────────────────────────────────
  'integration.http_request': [
    { key: 'url', label: 'URL', type: 'text', placeholder: 'https://api.example.com/v1/things', required: true },
    {
      key: 'method', label: 'Method', type: 'select',
      options: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map(m => ({ value: m, label: m })),
    },
    { key: 'headers', label: 'Headers', type: 'json', placeholder: '{ "Authorization": "Bearer …" }' },
    { key: 'body', label: 'Body', type: 'json', placeholder: '{ "text": "…" }' },
  ],
  'integration.send_email': [
    { key: 'to', label: 'To', type: 'text', placeholder: 'person@example.com', required: true },
    { key: 'subject', label: 'Subject', type: 'text' },
    { key: 'body', label: 'Body', type: 'textarea' },
    { key: 'from', label: 'From', type: 'text', placeholder: 'noreply@xoltra.local' },
    { key: 'host', label: 'SMTP host', type: 'text', placeholder: 'smtp.example.com', required: true },
    { key: 'port', label: 'SMTP port', type: 'number', min: 1, max: 65535, placeholder: '587' },
    { key: 'username', label: 'SMTP username', type: 'text' },
    {
      key: 'password', label: 'SMTP password', type: 'password',
      help: 'Stored in the workflow graph — use a per-app password, not your main one.',
    },
  ],

  // ─── Utilities ─────────────────────────────────────────────────────────────
  'utility.set_variable': [
    { key: 'variable_name', label: 'Variable name', type: 'text', placeholder: 'customer_id', required: true },
    {
      key: 'variable_value', label: 'Value', type: 'text',
      help: 'Leave empty to use the upstream value input instead.',
    },
  ],
  'utility.transform': [
    {
      key: 'template', label: 'Template (Jinja2)', type: 'textarea',
      placeholder: '{{ data.name }} scored {{ data.score }}',
      help: 'All upstream inputs are available as template variables. JSON output is auto-parsed.',
      required: true,
    },
  ],
  'utility.delay': [
    {
      key: 'seconds', label: 'Seconds', type: 'number', min: 0, max: 300, step: 1,
      placeholder: '1', help: 'Max 300 seconds (5 minutes).',
    },
  ],
};

/** Schema for a node type; null means "unknown — show the raw JSON editor". */
export function schemaFor(nodeType: string): ParamField[] | null {
  return PARAM_SCHEMAS[nodeType] ?? null;
}
