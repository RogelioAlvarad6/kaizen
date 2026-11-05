export type Field = {
  key: string;
  label: string;
  type: "text" | "textarea" | "select" | "multiselect" | "number" | "bool";
  options?: { value: string; label: string }[];
  default?: unknown;
  help?: string;
};

export type BlockMeta = {
  type: string;
  name: string;
  category: string;
  color: string;
  icon: string;
  description: string;
  fields: Field[];
  is_trigger: boolean;
  outputs: string[];
};

export type NodeData = { blockType: string; label: string; config: Record<string, unknown> };

export type Workflow = {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  graph: { nodes: any[]; edges: any[] };
  updated_at?: string;
};

export type Step = {
  node_id: string;
  label: string;
  type: string;
  status: "running" | "done" | "error";
  output?: string;
  error?: string;
  branch?: string | null;
  events?: string[];
  cost?: number;
  seconds?: number;
};

export type Run = {
  id: string;
  workflow_id: string;
  workflow_name: string;
  trigger: string;
  status: "running" | "success" | "error";
  input?: string;
  output?: string;
  error?: string;
  steps?: Step[];
  cost_usd: number;
  started_at: string;
  finished_at?: string;
};

export type DayTotals = { day: string; gym: number; reading: number; study: number; finance: number; other: number };
export type Streak = { current: number; best: number; rate30: number };
export type Progress = {
  days: DayTotals[];
  goals: { reading_goal_minutes: number; gym_goal_per_week: number; study_goal_minutes: number; current_cert: string };
  targets: { reading: number; study: number; gym: number };
  streaks: { reading: Streak; study: Streak; gym: Streak };
  gym_weeks: { week: string; sessions: number }[];
};

export type Goal = {
  id: number;
  name: string;
  category: "personal" | "professional";
  kind: "number" | "check";
  unit: string;
  target: number;
  period: "daily" | "weekly";
  step: number;
  sort: number;
  archived: number;
  deadline?: string | null;
  total_target?: number | null;
  start_date?: string | null;
  completed_at?: string | null;
};
export type Pace = {
  deadline: string;
  start_date: string;
  days_left: number;
  total: number;
  done: number;
  remaining: number;
  need_per_day: number;
  avg_per_day: number;
  gap_per_day: number;
  status: "on_pace" | "behind" | "done" | "overdue" | "completed";
};
export type DayGoal = Goal & { value: number; note: string; progress: number; met: boolean; pace: Pace | null };
export type GoalStats = {
  goal: Goal;
  daily: { day: string; value: number }[];
  weekly: { week: string; value: number }[];
  streak: { current: number; best: number; unit: string; rate: number; window: string };
  total_30: number;
  pace: Pace | null;
  burnup: { day: string; actual: number | null; plan: number }[] | null;
};

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      msg = (await res.json()).detail ?? msg;
    } catch {}
    throw new Error(msg);
  }
  return res.json();
}

export type Badge = { key: string; name: string; desc: string; earned_on: string | null };
export type XpSummary = {
  xp: number;
  level: number;
  title: string;
  level_floor: number;
  next_at: number;
  into_level: number;
  level_size: number;
  today: number;
  this_week: number;
  last_week: number;
  best_week: number;
  perfect_day_xp: number;
  daily: { day: string; xp: number }[];
  badges: Badge[];
  recent: { day: string; xp: number; reason: string; goal: string }[];
};

export type NotifyStatus = {
  configured: boolean;
  mention: boolean;
  settings: Record<string, string>;
  next_runs: Record<string, string | null>;
};

export const api = {
  notify: () => req<NotifyStatus>("/notify"),
  saveNotify: (s: Record<string, string>) => req<NotifyStatus>("/notify", { method: "PUT", body: JSON.stringify(s) }),
  sendNotify: (kind: string) => req<{ result: string }>(`/notify/send/${kind}`, { method: "POST" }),
  xp: () => req<XpSummary>("/xp"),
  completeGoal: (id: number, done = true) => req(`/goals/${id}/complete?done=${done}`, { method: "POST" }),
  goals: (all = false) => req<Goal[]>(`/goals${all ? "?include_archived=true" : ""}`),
  saveGoal: (g: Partial<Goal>) => req<Goal>("/goals", { method: "POST", body: JSON.stringify(g) }),
  archiveGoal: (id: number, archived = true) => req(`/goals/${id}/archive?archived=${archived}`, { method: "POST" }),
  day: (day: string) => req<{ day: string; week_start: string; goals: DayGoal[] }>(`/day/${day}`),
  log: (goal_id: number, day: string, value: number, note?: string) =>
    req("/log", { method: "POST", body: JSON.stringify({ goal_id, day, value, note }) }),
  stats: (days = 84) => req<{ today: string; goals: GoalStats[] }>(`/stats?days=${days}`),
  status: () => req<any>("/status"),
  blocks: () => req<{ blocks: BlockMeta[]; models: Record<string, any> }>("/blocks"),
  workflows: () => req<Workflow[]>("/workflows"),
  workflow: (id: string) => req<Workflow>(`/workflows/${id}`),
  saveWorkflow: (wf: Partial<Workflow>) => req<Workflow>("/workflows", { method: "POST", body: JSON.stringify(wf) }),
  deleteWorkflow: (id: string) => req(`/workflows/${id}`, { method: "DELETE" }),
  runWorkflow: (id: string, input: string) =>
    req<{ run_id: string }>(`/workflows/${id}/run`, { method: "POST", body: JSON.stringify({ input }) }),
  runs: (workflowId?: string) => req<Run[]>(`/runs${workflowId ? `?workflow_id=${workflowId}` : ""}`),
  run: (id: string) => req<Run>(`/runs/${id}`),
  chats: () => req<any[]>("/chats"),
  chat: (id: string) => req<any>(`/chats/${id}`),
  deleteChat: (id: string) => req(`/chats/${id}`, { method: "DELETE" }),
  sendChat: (chat_id: string | null, message: string, model?: string) =>
    req<any>("/chat", { method: "POST", body: JSON.stringify({ chat_id, message, model }) }),
  habits: (days = 14) => req<any>(`/habits?days=${days}`),
  progress: (days = 84) => req<Progress>(`/progress?days=${days}`),
  addHabit: (h: any) => req("/habits", { method: "POST", body: JSON.stringify(h) }),
  deleteHabit: (id: number) => req(`/habits/${id}`, { method: "DELETE" }),
  saveSettings: (s: Record<string, string>) => req("/settings", { method: "PUT", body: JSON.stringify(s) }),
};
