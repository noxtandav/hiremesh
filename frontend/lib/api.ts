/**
 * Thin API client for the Hiremesh backend.
 *
 * - Browser calls go to a relative `/api/...` path → Caddy → FastAPI. Cookies
 *   travel automatically because the browser sees a single origin.
 * - Server-side calls (RSC, route handlers, Next layouts) bypass Caddy and hit
 *   the API container directly inside the compose network. We forward the
 *   inbound `cookie` header so the call appears as the logged-in user.
 */

const isServer = typeof window === "undefined";
const PUBLIC_API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api";
const INTERNAL_API_BASE = process.env.INTERNAL_API_BASE ?? "http://api:8000";
const API_BASE = isServer ? INTERNAL_API_BASE : PUBLIC_API_BASE;

export type User = {
  id: number;
  email: string;
  name: string;
  role: "admin" | "recruiter";
  must_change_password: boolean;
  is_active: boolean;
};

export type Client = {
  id: number;
  name: string;
  notes: string | null;
  created_at: string;
};

// Returned by GET /clients (list). Detail/create/update endpoints return Client.
export type ClientWithStats = Client & {
  jobs_open: number;
  jobs_total: number;
  candidates_total: number;
  candidates_recent: number; // last 7 days
};

export type Stage = { id: number; name: string; position: number };

export type JobStatus = "open" | "on-hold" | "closed";
export type Job = {
  id: number;
  client_id: number;
  title: string;
  jd_text: string | null;
  location: string | null;
  exp_min: string | null;
  exp_max: string | null;
  ctc_min: string | null;
  ctc_max: string | null;
  status: JobStatus;
  created_at: string;
};
export type JobWithStages = Job & { stages: Stage[] };
// Returned by GET /jobs (list). Detail/create return JobWithStages.
export type JobWithStats = Job & {
  candidates_total: number;
  candidates_recent: number; // last 7 days
  moves_recent: number; // stage transitions in last 7 days
};

export type Candidate = {
  id: number;
  full_name: string;
  email: string | null;
  phone: string | null;
  location: string | null;
  current_company: string | null;
  current_title: string | null;
  total_exp_years: string | null;
  current_ctc: string | null;
  expected_ctc: string | null;
  notice_period_days: number | null;
  skills: string[];
  summary: string | null;
  deleted_at: string | null;
  created_at: string;
  created_by: number | null;
  // Hydrated by GET /candidates/{id}; null on the list endpoint.
  created_by_name: string | null;
};

export type Note = {
  id: number;
  candidate_id: number;
  author_id: number | null;
  body: string;
  created_at: string;
};

export type ResumeStatus = "pending" | "parsing" | "done" | "failed";
export type Resume = {
  id: number;
  candidate_id: number;
  filename: string;
  mime: string;
  is_primary: boolean;
  parse_status: ResumeStatus;
  parse_error: string | null;
  parsed_json: Record<string, unknown> | null;
  created_at: string;
};

export type CandidateJob = {
  id: number;
  candidate_id: number;
  job_id: number;
  current_stage_id: number;
  linked_at: string;
};

export type LastTransition = {
  at: string;
  by_user_id: number | null;
  by_user_name: string | null;
  from_stage_id: number | null;
  to_stage_id: number | null;
};

export type StageTransition = {
  id: number;
  candidate_id: number;
  job_id: number;
  from_stage_id: number | null;
  to_stage_id: number | null;
  by_user: number | null;
  at: string;
};

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown, message: string) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

type ReqInit = RequestInit & { cookie?: string };

async function request<T>(path: string, init: ReqInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }
  if (init.cookie) headers.set("cookie", init.cookie);

  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
    credentials: "include",
    cache: "no-store",
  });

  if (res.status === 204) return undefined as T;

  const text = await res.text();
  const body = text ? JSON.parse(text) : undefined;
  if (!res.ok) {
    const msg =
      typeof body?.detail === "string"
        ? body.detail
        : `Request failed with status ${res.status}`;
    throw new ApiError(res.status, body?.detail, msg);
  }
  return body as T;
}

const qs = (params: Record<string, string | number | boolean | undefined>) => {
  const e = Object.entries(params).filter(([, v]) => v !== undefined);
  return e.length ? `?${new URLSearchParams(e.map(([k, v]) => [k, String(v)]))}` : "";
};

export const api = {
  // auth
  login: (email: string, password: string) =>
    request<User>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  logout: () => request<void>("/auth/logout", { method: "POST" }),
  me: (cookie?: string) => request<User>("/auth/me", { cookie }),

  // clients
  listClients: (cookie?: string) =>
    request<ClientWithStats[]>("/clients", { cookie }),
  getClient: (id: number, cookie?: string) =>
    request<Client>(`/clients/${id}`, { cookie }),
  createClient: (data: { name: string; notes?: string }) =>
    request<Client>("/clients", { method: "POST", body: JSON.stringify(data) }),
  updateClient: (id: number, data: Partial<{ name: string; notes: string }>) =>
    request<Client>(`/clients/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  deleteClient: (id: number) =>
    request<void>(`/clients/${id}`, { method: "DELETE" }),

  // jobs
  listJobs: (
    params: { client_id?: number; status_filter?: JobStatus } = {},
    cookie?: string,
  ) => request<JobWithStats[]>(`/jobs${qs(params)}`, { cookie }),
  getJob: (id: number, cookie?: string) =>
    request<JobWithStages>(`/jobs/${id}`, { cookie }),
  createJob: (data: {
    client_id: number;
    title: string;
    jd_text?: string;
    location?: string;
    exp_min?: number;
    exp_max?: number;
    ctc_min?: number;
    ctc_max?: number;
    status?: JobStatus;
  }) => request<JobWithStages>("/jobs", { method: "POST", body: JSON.stringify(data) }),
  updateJob: (
    id: number,
    data: Partial<{
      title: string;
      jd_text: string;
      location: string;
      exp_min: number;
      exp_max: number;
      ctc_min: number;
      ctc_max: number;
      status: JobStatus;
    }>,
  ) =>
    request<Job>(`/jobs/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  deleteJob: (id: number) => request<void>(`/jobs/${id}`, { method: "DELETE" }),

  // candidates
  listCandidates: (
    params: { include_deleted?: boolean } = {},
    cookie?: string,
  ) => request<Candidate[]>(`/candidates${qs(params)}`, { cookie }),
  getCandidate: (id: number, cookie?: string) =>
    request<Candidate>(`/candidates/${id}`, { cookie }),
  createCandidate: (data: Partial<Candidate> & { full_name: string }) =>
    request<Candidate>("/candidates", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateCandidate: (id: number, data: Partial<Candidate>) =>
    request<Candidate>(`/candidates/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  deleteCandidate: (id: number) =>
    request<void>(`/candidates/${id}`, { method: "DELETE" }),
  restoreCandidate: (id: number) =>
    request<Candidate>(`/candidates/${id}/restore`, { method: "POST" }),
  listCandidateDuplicates: (id: number, cookie?: string) =>
    request<Candidate[]>(`/candidates/${id}/duplicates`, { cookie }),

  // notes
  listNotes: (candidateId: number, cookie?: string) =>
    request<Note[]>(`/candidates/${candidateId}/notes`, { cookie }),
  createNote: (candidateId: number, body: string) =>
    request<Note>(`/candidates/${candidateId}/notes`, {
      method: "POST",
      body: JSON.stringify({ body }),
    }),
  updateNote: (id: number, body: string) =>
    request<Note>(`/notes/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ body }),
    }),
  deleteNote: (id: number) =>
    request<void>(`/notes/${id}`, { method: "DELETE" }),

  // ask
  askCandidate: (candidateId: number, question: string) =>
    request<{
      answer: string;
      citations: {
        type: string;
        id: number | null;
        snippet: string;
        score: number | null;
        percentile: number | null;
      }[];
    }>(`/ask/candidate/${candidateId}`, {
      method: "POST",
      body: JSON.stringify({ question }),
    }),
  askPool: (question: string) =>
    request<{
      answer: string;
      citations: {
        type: string;
        id: number | null;
        snippet: string;
        score: number | null;
        percentile: number | null;
      }[];
      route: "structured" | "semantic" | "hybrid";
      matched_count: number | null;
      rows: Record<string, unknown>[] | null;
    }>("/ask/pool", {
      method: "POST",
      body: JSON.stringify({ question }),
    }),

  // search
  searchCandidates: (
    body: {
      q?: string;
      location?: string;
      skills?: string[];
      exp_min?: number;
      exp_max?: number;
      stage_name?: string;
      limit?: number;
      offset?: number;
    },
    cookie?: string,
  ) =>
    request<{ candidate: Candidate; score: number | null }[]>(
      "/search/candidates",
      { method: "POST", body: JSON.stringify(body), cookie },
    ),

  // admin
  reindexCandidates: () =>
    request<{ enqueued: number }>("/admin/reindex/candidates", {
      method: "POST",
    }),
  resetEmbeddings: (skipProbe = false) =>
    request<{ reset: boolean; dim: number; enqueued: number }>(
      `/admin/embeddings/reset?confirm=true${skipProbe ? "&skip_probe=true" : ""}`,
      { method: "POST" },
    ),
  reparseAllResumesPreview: () =>
    request<{ would_enqueue: number; warning: string }>(
      "/admin/reparse/resumes",
      { method: "POST" },
    ),
  reparseAllResumesConfirm: () =>
    request<{ reparsed: true; enqueued: number }>(
      "/admin/reparse/resumes?confirm=true",
      { method: "POST" },
    ),
  listUsers: (cookie?: string) => request<User[]>("/users", { cookie }),
  updateUser: (
    id: number,
    data: Partial<{ name: string; role: "admin" | "recruiter"; is_active: boolean }>,
  ) =>
    request<User>(`/users/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  resetUserPassword: (id: number, newPassword: string) =>
    request<User>(`/users/${id}/reset-password`, {
      method: "POST",
      body: JSON.stringify({ new_password: newPassword }),
    }),
  createUser: (data: {
    email: string;
    name: string;
    password: string;
    role: "admin" | "recruiter";
  }) =>
    request<User>("/users", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  listAudit: (
    params: { entity?: string; action?: string; limit?: number; offset?: number } = {},
    cookie?: string,
  ) =>
    request<
      {
        id: number;
        actor_id: number | null;
        actor_name: string | null;
        action: string;
        entity: string;
        entity_id: number | null;
        payload: Record<string, unknown> | null;
        at: string;
      }[]
    >(`/admin/audit-log${qs(params)}`, { cookie }),
  getMetrics: (cookie?: string) =>
    request<{
      candidates: { active: number; soft_deleted: number; embedded: number; embedding_coverage: number };
      clients: { total: number };
      jobs: { open: number; on_hold: number; closed: number };
      resumes: { pending: number; parsing: number; done: number; failed: number };
      users: { total: number; active: number };
      queue: { celery_pending: number | null };
      models: { parse: string; embed: string; embed_dim: number; qa: string };
    }>("/admin/metrics", { cookie }),

  // pipeline
  getBoard: (jobId: number, cookie?: string) =>
    request<
      {
        stage: Stage;
        links: (CandidateJob & {
          candidate: Candidate;
          last_transition: LastTransition | null;
        })[];
      }[]
    >(`/jobs/${jobId}/board`, { cookie }),
  linkCandidateToJob: (jobId: number, candidateId: number) =>
    request<CandidateJob>(`/jobs/${jobId}/candidates`, {
      method: "POST",
      body: JSON.stringify({ candidate_id: candidateId }),
    }),
  moveLink: (linkId: number, stageId: number) =>
    request<CandidateJob>(`/candidate-jobs/${linkId}`, {
      method: "PATCH",
      body: JSON.stringify({ stage_id: stageId }),
    }),
  unlink: (linkId: number) =>
    request<void>(`/candidate-jobs/${linkId}`, { method: "DELETE" }),
  listTransitions: (linkId: number, cookie?: string) =>
    request<StageTransition[]>(`/candidate-jobs/${linkId}/transitions`, { cookie }),
  listLinkNotes: (linkId: number, cookie?: string) =>
    request<Note[]>(`/candidate-jobs/${linkId}/notes`, { cookie }),
  createLinkNote: (linkId: number, body: string) =>
    request<Note>(`/candidate-jobs/${linkId}/notes`, {
      method: "POST",
      body: JSON.stringify({ body }),
    }),

  // resumes
  listResumes: (candidateId: number, cookie?: string) =>
    request<Resume[]>(`/candidates/${candidateId}/resumes`, { cookie }),
  bulkImportCandidates: async (files: File[]) => {
    const fd = new FormData();
    for (const f of files) fd.append("files", f);
    const res = await fetch(`${API_BASE}/candidates/bulk-import`, {
      method: "POST",
      body: fd,
      credentials: "include",
      cache: "no-store",
    });
    if (!res.ok) {
      const text = await res.text();
      let detail: unknown;
      try {
        detail = JSON.parse(text)?.detail;
      } catch {
        detail = text;
      }
      throw new ApiError(
        res.status,
        detail,
        typeof detail === "string" ? detail : `Bulk import failed (${res.status})`,
      );
    }
    return (await res.json()) as {
      imported: number;
      total: number;
      results: {
        filename: string;
        status: "ok" | "error";
        candidate_id?: number;
        resume_id?: number;
        placeholder_name?: string;
        error?: string;
      }[];
    };
  },
  uploadResume: async (candidateId: number, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(`${API_BASE}/candidates/${candidateId}/resumes`, {
      method: "POST",
      body: fd,
      credentials: "include",
      cache: "no-store",
    });
    if (!res.ok) {
      const text = await res.text();
      let detail: unknown;
      try {
        detail = JSON.parse(text)?.detail;
      } catch {
        detail = text;
      }
      throw new ApiError(
        res.status,
        detail,
        typeof detail === "string" ? detail : `Upload failed (${res.status})`,
      );
    }
    return (await res.json()) as Resume;
  },
  setPrimaryResume: (id: number) =>
    request<Resume>(`/resumes/${id}/primary`, { method: "POST" }),
  reparseResume: (id: number) =>
    request<Resume>(`/resumes/${id}/reparse`, { method: "POST" }),
  deleteResume: (id: number) =>
    request<void>(`/resumes/${id}`, { method: "DELETE" }),
  getResumeUrl: (id: number) =>
    request<{ url: string; expires_in: number }>(`/resumes/${id}/url`),
  /**
   * Same-origin path that streams resume bytes through the API. Use for
   * iframe `src` and download links so it works regardless of where the
   * user's browser is (LAN, WAN, etc.) — no dependency on S3_PUBLIC_ENDPOINT
   * being reachable from the client.
   */
  resumeFilePath: (id: number, opts: { download?: boolean } = {}) =>
    `${PUBLIC_API_BASE}/resumes/${id}/file${opts.download ? "?download=true" : ""}`,

  // stages
  getStageTemplate: (cookie?: string) =>
    request<Stage[]>("/stages/template", { cookie }),
  updateStageTemplate: (
    stages: { id?: number; name: string }[],
  ) =>
    request<Stage[]>("/stages/template", {
      method: "PUT",
      body: JSON.stringify({ stages }),
    }),
};
