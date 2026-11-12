export type AIJobState =
  | "queued"
  | "running"
  | "retry_wait"
  | "cancelling"
  | "cancelled"
  | "succeeded"
  | "failed";

export type AIJob = {
  job_id: string;
  state: AIJobState;
  attempt_count: number;
  cancel_requested: boolean;
  report_id: string | null;
  error: { code: string; retryable: boolean; message: string } | null;
  available_at: string;
  requested_at: string;
  started_at: string | null;
  completed_at: string | null;
};

export function isActiveJob(job: AIJob): boolean {
  return ["queued", "running", "retry_wait", "cancelling"].includes(job.state);
}

export function jobLabel(job: AIJob): string {
  switch (job.state) {
    case "queued": return "Waiting to start";
    case "running": return "Investigating";
    case "retry_wait": return "Retry scheduled";
    case "cancelling": return "Cancelling";
    case "cancelled": return "Cancelled";
    case "succeeded": return "Completed";
    case "failed": return "Failed";
  }
}
