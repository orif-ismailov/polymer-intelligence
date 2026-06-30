/**
 * C-07 — Request Detail screen ("Детали заявки").
 *
 * Reads :id from URL params, calls api.getRequest(id), renders:
 *   - Request fields (product, volume, target price, incoterms, comment)
 *   - Attached files list (name + size)
 *   - StatusChip (current status)
 *   - StatusTimeline (full history in Asia/Tashkent, D-11)
 *   - ErrorBanner on load failure
 *
 * BackButton → /requests (C-06).
 *
 * T-03-18: getRequest() is initData-scoped on the backend — cross-client
 * ids return 404; the frontend shows the load error banner for any failure.
 */

import { useEffect, useState, type CSSProperties } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Download, FileText } from "lucide-react";
import { styles } from "../App";
import { api } from "../api/client";
import { backButton, mainButton } from "../telegram";
import StatusChip from "../components/StatusChip";
import StatusTimeline from "../components/StatusTimeline";
import ErrorBanner from "../components/ErrorBanner";
import type { RequestDetail, RequestFileMeta } from "../types";

// ── Attached file row: inline image preview, or an openable/downloadable file ──

function RequestFileRow({ requestId, file }: { requestId: number; file: RequestFileMeta }) {
  const isImage = (file.mime_type ?? "").startsWith("image/");
  const [imgUrl, setImgUrl] = useState<string | null>(null);

  // Image files: fetch the (owner-only) bytes with the initData header and show inline.
  useEffect(() => {
    if (!isImage) return;
    let url: string | null = null;
    let cancelled = false;
    api
      .getRequestFile(requestId, file.id)
      .then((blob) => {
        if (cancelled) return;
        url = URL.createObjectURL(blob);
        setImgUrl(url);
      })
      .catch(() => {
        /* leave without a preview */
      });
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [isImage, requestId, file.id]);

  // Tap → open the file in a new tab (PDF/image render; other types download).
  async function openFile() {
    try {
      const blob = await api.getRequestFile(requestId, file.id);
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank", "noopener");
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch {
      /* ignore */
    }
  }

  if (isImage) {
    return (
      <button
        type="button"
        onClick={() => void openFile()}
        style={{ display: "block", width: "100%", padding: 0, marginBottom: "10px", background: "none", border: "none", cursor: "pointer", textAlign: "left" }}
      >
        {imgUrl ? (
          <img
            src={imgUrl}
            alt={file.file_name}
            style={{ width: "100%", maxHeight: "240px", objectFit: "cover", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: "var(--surface-2)" }}
          />
        ) : (
          <span style={{ display: "block", width: "100%", height: "120px", borderRadius: "var(--r-sm)", background: "var(--surface-2)" }} />
        )}
        <span style={{ display: "block", fontSize: "12px", color: "var(--text-muted)", marginTop: "4px" }}>{file.file_name}</span>
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={() => void openFile()}
      style={{ display: "flex", alignItems: "center", gap: "10px", width: "100%", padding: "10px 0", background: "none", border: "none", borderBottom: "1px solid var(--border)", cursor: "pointer", textAlign: "left" }}
    >
      <FileText size={18} color="var(--blue)" style={{ flex: "0 0 auto" }} />
      <span style={{ flex: 1, minWidth: 0, fontSize: "13px", color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {file.file_name}
      </span>
      <span style={{ fontSize: "12px", color: "var(--text-muted)", flex: "0 0 auto" }}>{formatBytes(file.size_bytes)}</span>
      <Download size={16} color="var(--text-muted)" style={{ flex: "0 0 auto" }} />
    </button>
  );
}

// ── Size formatting ────────────────────────────────────────────────────────────

function formatBytes(bytes: number | null): string {
  if (bytes === null || bytes === undefined) return "";
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${Math.round(bytes / 1024)} KB`;
}

// ── Detail field row ───────────────────────────────────────────────────────────

function DetailRow({ label, value }: { label: string; value: string | null | undefined }) {
  if (!value) return null;
  return (
    <div style={{ marginBottom: "10px" } as CSSProperties}>
      <span
        style={{
          display: "block",
          fontSize: "12px",
          color: "var(--text-muted)",
          marginBottom: "2px",
        } as CSSProperties}
      >
        {label}
      </span>
      <span
        style={{
          fontSize: "14px",
          color: "var(--text)",
        } as CSSProperties}
      >
        {value}
      </span>
    </div>
  );
}

// ── Loading skeleton ───────────────────────────────────────────────────────────

function DetailSkeleton() {
  return (
    <>
      <style>
        {`@keyframes pulse-detail {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }`}
      </style>
      {[80, 60, 60, 120, 100].map((h, i) => (
        <div
          key={i}
          style={{
            height: `${h}px`,
            borderRadius: "var(--r-md)",
            backgroundColor: "var(--surface)",
            border: "1px solid var(--border)",
            marginBottom: "12px",
            animation: "pulse-detail 1.4s ease-in-out infinite",
          } as CSSProperties}
        />
      ))}
    </>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function RequestDetailPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();

  const [detail, setDetail] = useState<RequestDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      const numId = id ? parseInt(id, 10) : NaN;
      if (isNaN(numId)) {
        setError(t("error.loadFailed"));
        setLoading(false);
        return;
      }
      try {
        const data = await api.getRequest(numId);
        setDetail(data);
      } catch {
        setError(t("error.loadFailed"));
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, [id, t]);

  // Telegram BackButton → /requests
  useEffect(() => {
    backButton.show();
    const cleanup = backButton.onClick(() => navigate("/requests"));
    mainButton.hide();
    return () => {
      cleanup();
      backButton.hide();
    };
  }, [navigate]);

  return (
    <div style={{ ...styles.app }}>
      {/* Screen header */}
      <div style={styles.header as CSSProperties}>
        <h1 style={styles.headerTitle}>{t("requestDetail.title")}</h1>
        {detail && (
          <p style={styles.headerSubtitle as CSSProperties}>{detail.number}</p>
        )}
      </div>

      <div style={{ padding: "16px" }}>
        {/* Error banner */}
        {error && <ErrorBanner message={error} />}

        {/* Loading state */}
        {loading && <DetailSkeleton />}

        {/* Detail content */}
        {!loading && detail && (
          <>
            {/* Status + number card */}
            <div style={{ ...styles.card as CSSProperties, marginBottom: "12px" }}>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: "8px",
                } as CSSProperties}
              >
                <span
                  style={{
                    fontSize: "15px",
                    fontWeight: 600,
                    color: "var(--text)",
                  } as CSSProperties}
                >
                  {detail.number}
                </span>
                <StatusChip status={detail.status} />
              </div>
            </div>

            {/* Request fields card */}
            <div style={{ ...styles.card as CSSProperties, marginBottom: "12px" }}>
              <DetailRow
                label={t("wizard.product")}
                value={`ID ${detail.product_id}`}
              />
              {detail.grade_text && (
                <DetailRow label={t("wizard.grade")} value={detail.grade_text} />
              )}
              {detail.polymer_type && (
                <DetailRow label={t("wizard.polymerType")} value={detail.polymer_type} />
              )}
              <DetailRow
                label={t("wizard.volume")}
                value={`${detail.volume} ${detail.volume_unit}`}
              />
              {detail.target_price && (
                <DetailRow
                  label={t("wizard.targetPrice")}
                  value={`${detail.target_price} ${detail.currency}`}
                />
              )}
              {detail.incoterms && detail.incoterms !== "unknown" && (
                <DetailRow label={t("wizard.incoterms")} value={detail.incoterms} />
              )}
              <DetailRow
                label={t("wizard.destinationCountry")}
                value={detail.destination_country}
              />
              {detail.port_or_city && (
                <DetailRow label={t("wizard.portOrCity")} value={detail.port_or_city} />
              )}
              {detail.desired_date && (
                <DetailRow label={t("wizard.desiredDate")} value={detail.desired_date} />
              )}
              <DetailRow
                label={t("wizard.validityDays")}
                value={`${detail.validity_days}`}
              />
              <DetailRow label={t("wizard.urgency")} value={detail.urgency} />
              {detail.comment && (
                <DetailRow label={t("wizard.comment")} value={detail.comment} />
              )}
            </div>

            {/* Attached files */}
            {detail.files.length > 0 && (
              <div style={{ ...styles.card as CSSProperties, marginBottom: "12px" }}>
                <h3
                  style={{
                    margin: "0 0 10px",
                    fontSize: "14px",
                    fontWeight: 600,
                    color: "var(--text)",
                  } as CSSProperties}
                >
                  {t("requestDetail.files")}
                </h3>
                {detail.files.map((file) => (
                  <RequestFileRow key={file.id} requestId={detail.id} file={file} />
                ))}
              </div>
            )}

            {/* Status history timeline */}
            {detail.history.length > 0 && (
              <div style={{ ...styles.card as CSSProperties }}>
                <StatusTimeline history={detail.history} />
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
