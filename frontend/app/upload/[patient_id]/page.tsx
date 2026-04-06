"use client";

import React, { useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { format } from "date-fns";
import { CalendarDays, Upload, PlayCircle, CheckCircle2, Loader2, AlertCircle, ChevronRight } from "lucide-react";

import AuthGuard         from "@/components/layout/AuthGuard";
import DashboardLayout   from "@/components/layout/DashboardLayout";
import SequenceDropzone  from "@/components/upload/SequenceDropzone";
import SequenceChecklist from "@/components/upload/SequenceChecklist";
import ClinicalFlag      from "@/components/ui/ClinicalFlag";

import { createScan, uploadSequenceFile, runScanPipeline, type ClinicalMetadata } from "@/lib/api";
import { SEQUENCES, FLAG_MESSAGES, type Sequence } from "@/lib/constants";
import type { SequenceFile } from "@/components/upload/SequenceDropzone";

function StepIndicator({ step, current, label }: { step: number; current: number; label: string }) {
  const done   = step < current;
  const active = step === current;
  return (
    <div className="flex items-center gap-2">
      <div
        className="flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-bold shrink-0 transition-all duration-200 border"
        style={{
          backgroundColor: done ? "var(--green-dim)" : active ? "var(--blue-dim)" : "var(--surface-2)",
          color:           done ? "var(--green)"     : active ? "var(--blue)"     : "var(--muted)",
          borderColor:     done ? "var(--green)"     : active ? "var(--blue)"     : "var(--border)",
        }}
      >
        {done ? <CheckCircle2 size={12} /> : step}
      </div>
      <span className="text-[12px] font-medium" style={{ color: active ? "var(--text)" : "var(--muted)" }}>
        {label}
      </span>
    </div>
  );
}

interface UploadProgress { pct: number; done: boolean; error: string | null; }

export default function UploadPage() {
  const params     = useParams();
  const router     = useRouter();
  const patient_id = params.patient_id as string;

  const [step, setStep] = useState<1 | 2 | 3>(1);
  const today = format(new Date(), "yyyy-MM-dd");
  const [scanDate, setScanDate] = useState(today);
  const [scanId, setScanId]     = useState<string | null>(null);
  const [step1Loading, setStep1Loading] = useState(false);
  const [step1Error,   setStep1Error  ] = useState<string | null>(null);

  const [files, setFiles] = useState<Partial<Record<Sequence, SequenceFile | null>>>({});
  const [uploadProgress, setUploadProgress] = useState<Partial<Record<Sequence, UploadProgress>>>({});
  const [uploading,    setUploading   ] = useState(false);
  const [uploadError,  setUploadError ] = useState<string | null>(null);

  const [steroidCurrent,        setSteroidCurrent       ] = useState<string>("");
  const [steroidBaseline,       setSteroidBaseline      ] = useState<string>("");
  const [newLesion,             setNewLesion            ] = useState(false);
  const [weeksRt,               setWeeksRt              ] = useState<string>("");
  const [clinicalDeterioration, setClinicalDeterioration] = useState(false);
  const [mgmtStatus,            setMgmtStatus           ] = useState<string>("unknown");
  const [idhStatus,             setIdhStatus            ] = useState<string>("unknown");
  const [daysSinceDiagnosis,    setDaysSinceDiagnosis   ] = useState<string>("");

  const [running,  setRunning ] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  const allReady = SEQUENCES.every((s) => files[s] && !files[s]!.oversized);

  async function handleDateConfirm() {
    setStep1Loading(true); setStep1Error(null);
    try {
      const scan = await createScan(patient_id, scanDate);
      setScanId(scan.scan_id); setStep(2);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setStep1Error(detail ?? "Failed to create scan record.");
    } finally { setStep1Loading(false); }
  }

  const handleUploadAll = useCallback(async () => {
    if (!scanId || !allReady) return;
    setUploading(true); setUploadError(null);
    const initProgress: Partial<Record<Sequence, UploadProgress>> = {};
    SEQUENCES.forEach((s) => { initProgress[s] = { pct: 0, done: false, error: null }; });
    setUploadProgress(initProgress);
    let anyError = false;
    await Promise.all(SEQUENCES.map(async (seq) => {
      const seqFile = files[seq];
      if (!seqFile) return;
      try {
        await uploadSequenceFile(scanId, seq, seqFile.file, (pct) =>
          setUploadProgress((prev) => ({ ...prev, [seq]: { pct, done: false, error: null } }))
        );
        setUploadProgress((prev) => ({ ...prev, [seq]: { pct: 100, done: true, error: null } }));
      } catch (err: unknown) {
        const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Upload failed";
        setUploadProgress((prev) => ({ ...prev, [seq]: { pct: 0, done: false, error: detail } }));
        anyError = true;
      }
    }));
    setUploading(false);
    if (anyError) setUploadError("One or more sequences failed to upload. Please retry.");
    else setStep(3);
  }, [scanId, allReady, files]);

  async function handleRun() {
    if (!scanId) return;
    setRunning(true); setRunError(null);
    try {
      await runScanPipeline(scanId, {
        steroid_dose_current_mg:   steroidCurrent       ? parseFloat(steroidCurrent)       : null,
        steroid_dose_baseline_mg:  steroidBaseline      ? parseFloat(steroidBaseline)      : null,
        new_lesion_detected:       newLesion,
        weeks_since_rt_completion: weeksRt              ? parseInt(weeksRt)                : null,
        clinical_deterioration:    clinicalDeterioration,
        mgmt_status:               mgmtStatus,
        idh_status:                idhStatus,
        days_since_diagnosis:      daysSinceDiagnosis   ? parseInt(daysSinceDiagnosis)     : null,
      });
      router.push(`/status/${scanId}`);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setRunError(detail ?? "Failed to start pipeline.");
      setRunning(false);
    }
  }

  const inputClass = "w-full px-3.5 py-2.5 rounded-lg text-sm font-mono border focus:outline-none transition-colors duration-150";
  const inputStyle = { backgroundColor: "var(--bg)", borderColor: "var(--border)", color: "var(--text)" };

  return (
    <AuthGuard>
      <DashboardLayout>
        <div className="max-w-[720px] mx-auto space-y-6">

          {/* Header */}
          <div>
            <h2 className="text-[18px] font-bold" style={{ color: "var(--text)" }}>Upload Scan</h2>
            <p className="text-[12px] mt-0.5 font-mono" style={{ color: "var(--muted)" }}>Patient: {patient_id}</p>
          </div>

          {/* Step indicator */}
          <div className="flex items-center gap-3 px-5 py-3.5 rounded-xl border" style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)" }}>
            <StepIndicator step={1} current={step} label="Scan date" />
            <ChevronRight size={12} className="shrink-0" style={{ color: "var(--border)" }} />
            <StepIndicator step={2} current={step} label="Upload sequences" />
            <ChevronRight size={12} className="shrink-0" style={{ color: "var(--border)" }} />
            <StepIndicator step={3} current={step} label="Review & run" />
          </div>

          {/* Step 1 */}
          {step === 1 && (
            <div className="rounded-xl border p-6 space-y-5" style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)" }}>
              <div>
                <h3 className="text-[14px] font-bold mb-1" style={{ color: "var(--text)" }}>Select scan date</h3>
                <p className="text-[12px]" style={{ color: "var(--muted)" }}>The date the MRI scan was acquired, not today's date.</p>
              </div>
              {step1Error && (
                <div className="flex items-start gap-2 px-3 py-2.5 rounded-lg border" style={{ backgroundColor: "var(--red-dim)", borderColor: "var(--red)" }}>
                  <AlertCircle size={13} className="mt-0.5 shrink-0" style={{ color: "var(--red)" }} />
                  <p className="text-[12px]" style={{ color: "var(--red)" }}>{step1Error}</p>
                </div>
              )}
              <div>
                <label className="block text-[11px] font-semibold uppercase tracking-wider mb-1.5" style={{ color: "var(--muted)" }}>Scan date</label>
                <input
                  type="date" value={scanDate} max={today} onChange={(e) => setScanDate(e.target.value)}
                  className={inputClass + " [color-scheme:dark]"} style={inputStyle}
                />
              </div>
              <button
                onClick={handleDateConfirm} disabled={!scanDate || step1Loading}
                className="flex items-center gap-2 px-5 py-2.5 rounded-lg text-white text-[13px] font-semibold disabled:opacity-40 disabled:cursor-not-allowed transition-all duration-150"
                style={{ background: "linear-gradient(to right, var(--blue), #1557b0)" }}
              >
                {step1Loading ? <><Loader2 size={13} className="animate-spin" /> Creating scan…</> : <><CalendarDays size={13} /> Confirm date</>}
              </button>
            </div>
          )}

          {/* Step 2 */}
          {step === 2 && (
            <div className="space-y-5">
              <div className="rounded-xl border p-6" style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)" }}>
                <h3 className="text-[14px] font-bold mb-1" style={{ color: "var(--text)" }}>Upload DICOM sequences</h3>
                <p className="text-[12px] mb-5" style={{ color: "var(--muted)" }}>All four sequences are required. Drop DICOM files into each zone.</p>
                <div className="grid grid-cols-2 gap-3">
                  {SEQUENCES.map((seq) => (
                    <SequenceDropzone key={seq} sequence={seq} value={files[seq] ?? null}
                      onChange={(f) => setFiles((prev) => ({ ...prev, [seq]: f }))} disabled={uploading} />
                  ))}
                </div>

                {uploading && (
                  <div className="mt-5 space-y-2">
                    {SEQUENCES.map((seq) => {
                      const prog = uploadProgress[seq];
                      if (!prog) return null;
                      const barColor = prog.error ? "var(--red)" : prog.done ? "var(--green)" : "var(--blue)";
                      return (
                        <div key={seq} className="flex items-center gap-3">
                          <span className="text-[10px] font-bold font-mono w-10 shrink-0" style={{ color: "var(--muted)" }}>{seq}</span>
                          <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ backgroundColor: "var(--surface-2)" }}>
                            <div className="h-full rounded-full transition-all duration-200" style={{ width: `${prog.pct}%`, backgroundColor: barColor }} />
                          </div>
                          <span className="text-[10px] font-mono w-8 text-right shrink-0" style={{ color: "var(--muted)" }}>
                            {prog.error ? "err" : prog.done ? "✓" : `${prog.pct}%`}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                )}

                {uploadError && (
                  <div className="mt-4 flex items-start gap-2 px-3 py-2.5 rounded-lg border" style={{ backgroundColor: "var(--red-dim)", borderColor: "var(--red)" }}>
                    <AlertCircle size={13} className="mt-0.5 shrink-0" style={{ color: "var(--red)" }} />
                    <p className="text-[12px]" style={{ color: "var(--red)" }}>{uploadError}</p>
                  </div>
                )}

                <button
                  onClick={handleUploadAll} disabled={!allReady || uploading}
                  className="mt-5 flex items-center gap-2 px-5 py-2.5 rounded-lg text-white text-[13px] font-semibold disabled:opacity-40 disabled:cursor-not-allowed transition-all duration-150"
                  style={{ background: "linear-gradient(to right, var(--blue), #1557b0)" }}
                >
                  {uploading ? <><Loader2 size={13} className="animate-spin" /> Uploading…</> : <><Upload size={13} /> Upload all sequences</>}
                </button>
              </div>
              <SequenceChecklist files={files} />
            </div>
          )}

          {/* Step 3 */}
          {step === 3 && scanId && (
            <div className="rounded-xl border p-6 space-y-5" style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)" }}>
              <div>
                <h3 className="text-[14px] font-bold mb-1" style={{ color: "var(--text)" }}>Clinical metadata</h3>
                <p className="text-[12px]" style={{ color: "var(--muted)" }}>Required for RANO classification. Leave blank if not applicable (first scan).</p>
              </div>

              <div className="grid grid-cols-2 gap-4">
                {[
                  { label: "Current steroid dose (mg/day)",  val: steroidCurrent,  set: setSteroidCurrent,  placeholder: "e.g. 4" },
                  { label: "Baseline steroid dose (mg/day)", val: steroidBaseline, set: setSteroidBaseline, placeholder: "e.g. 2" },
                ].map(({ label, val, set, placeholder }) => (
                  <div key={label}>
                    <label className="block text-[11px] font-semibold uppercase tracking-wider mb-1.5" style={{ color: "var(--muted)" }}>{label}</label>
                    <input type="number" min="0" step="0.5" value={val} onChange={(e) => set(e.target.value)} placeholder={placeholder} className={inputClass} style={inputStyle} />
                  </div>
                ))}
              </div>

              <div>
                <label className="block text-[11px] font-semibold uppercase tracking-wider mb-1.5" style={{ color: "var(--muted)" }}>Weeks since RT completion</label>
                <input type="number" min="0" value={weeksRt} onChange={(e) => setWeeksRt(e.target.value)} placeholder="e.g. 12" className={inputClass} style={inputStyle} />
              </div>

              {/* MGMT + IDH dropdowns */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-[11px] font-semibold uppercase tracking-wider mb-1.5" style={{ color: "var(--muted)" }}>
                    MGMT Methylation Status
                  </label>
                  <select
                    value={mgmtStatus}
                    onChange={(e) => setMgmtStatus(e.target.value)}
                    className={inputClass}
                    style={inputStyle}
                  >
                    <option value="unknown">Unknown</option>
                    <option value="methylated">Methylated</option>
                    <option value="unmethylated">Unmethylated</option>
                  </select>
                </div>
                <div>
                  <label className="block text-[11px] font-semibold uppercase tracking-wider mb-1.5" style={{ color: "var(--muted)" }}>
                    IDH Mutation Status
                  </label>
                  <select
                    value={idhStatus}
                    onChange={(e) => setIdhStatus(e.target.value)}
                    className={inputClass}
                    style={inputStyle}
                  >
                    <option value="unknown">Unknown</option>
                    <option value="mutant">Mutant</option>
                    <option value="wild_type">Wild-type</option>
                  </select>
                </div>
              </div>

              {/* Days since diagnosis */}
              <div>
                <label className="block text-[11px] font-semibold uppercase tracking-wider mb-1.5" style={{ color: "var(--muted)" }}>
                  Days since diagnosis <span style={{ color: "var(--muted)", fontWeight: 400 }}>(optional)</span>
                </label>
                <input
                  type="number"
                  min="0"
                  value={daysSinceDiagnosis}
                  onChange={(e) => setDaysSinceDiagnosis(e.target.value)}
                  placeholder="e.g. 180"
                  className={inputClass}
                  style={inputStyle}
                />
              </div>

              <div className="space-y-3">
                {[
                  { label: "New lesion detected", value: newLesion, set: setNewLesion },
                  { label: "Clinical deterioration", value: clinicalDeterioration, set: setClinicalDeterioration },
                ].map(({ label, value, set }) => (
                  <label key={label} className="flex items-center gap-3 cursor-pointer">
                    <div
                      onClick={() => set(!value)}
                      className="w-4 h-4 rounded border flex items-center justify-center shrink-0 transition-colors"
                      style={{ backgroundColor: value ? "var(--blue)" : "var(--bg)", borderColor: value ? "var(--blue)" : "var(--border)" }}
                    >
                      {value && <CheckCircle2 size={10} className="text-white" />}
                    </div>
                    <span className="text-[12px]" style={{ color: "var(--muted)" }}>{label}</span>
                  </label>
                ))}
              </div>

              <hr style={{ borderColor: "var(--border)" }} />

              <h3 className="text-[14px] font-bold" style={{ color: "var(--text)" }}>Review & launch</h3>
              <div className="rounded-lg border overflow-hidden" style={{ borderColor: "var(--border)" }}>
                {[
                  { label: "Patient ID", value: patient_id },
                  { label: "Scan ID",    value: scanId     },
                  { label: "Scan date",  value: format(new Date(scanDate + "T00:00:00"), "dd MMMM yyyy") },
                  { label: "Sequences",  value: SEQUENCES.join(", ") },
                ].map((row) => (
                  <div key={row.label} className="flex items-center justify-between px-4 py-3 border-b last:border-0" style={{ borderColor: "var(--border)" }}>
                    <span className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: "var(--muted)" }}>{row.label}</span>
                    <span className="text-[12px] font-mono" style={{ color: "var(--text)" }}>{row.value}</span>
                  </div>
                ))}
              </div>

              <ClinicalFlag variant="warning" message={FLAG_MESSAGES.disclaimer} compact />

              {runError && (
                <div className="flex items-start gap-2 px-3 py-2.5 rounded-lg border" style={{ backgroundColor: "var(--red-dim)", borderColor: "var(--red)" }}>
                  <AlertCircle size={13} className="mt-0.5 shrink-0" style={{ color: "var(--red)" }} />
                  <p className="text-[12px]" style={{ color: "var(--red)" }}>{runError}</p>
                </div>
              )}

              <button
                onClick={handleRun} disabled={running}
                className="flex items-center gap-2 px-6 py-3 rounded-lg text-white text-[13px] font-semibold disabled:opacity-40 disabled:cursor-not-allowed transition-all duration-150"
                style={{ background: "linear-gradient(to right, var(--blue), #1557b0)" }}
              >
                {running ? <><Loader2 size={14} className="animate-spin" /> Starting pipeline…</> : <><PlayCircle size={14} /> Launch pipeline</>}
              </button>
            </div>
          )}
        </div>
      </DashboardLayout>
    </AuthGuard>
  );
}