import { useEffect, useRef, useState } from "react";
import type { JobSummary } from "@/lib/api";

export function useElapsedSeconds(job: JobSummary | null): number {
  const startRef = useRef<number>(Date.now());
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    startRef.current = Date.now();
  }, [job?.job_id]);

  useEffect(() => {
    if (!job || (job.status !== "queued" && job.status !== "processing")) return;
    const tick = setInterval(() => {
      setElapsed(Math.round((Date.now() - startRef.current) / 1000));
    }, 1000);
    return () => clearInterval(tick);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.status]);

  return elapsed;
}
