import { postmortemDownloadPath } from "@/lib/postmortem-routes";

import styles from "./postmortem-exports.module.css";

export function PostmortemExports({
  incidentId,
  versionId,
}: {
  incidentId: string;
  versionId: string;
}) {
  return (
    <nav aria-label="Download finalized postmortem" className={styles.actions}>
      <a
        className={styles.primary}
        href={postmortemDownloadPath(incidentId, versionId, "pdf")}
        download
      >
        Download PDF
      </a>
      <a
        className={styles.secondary}
        href={postmortemDownloadPath(incidentId, versionId, "json")}
        download
      >
        Download JSON
      </a>
    </nav>
  );
}
