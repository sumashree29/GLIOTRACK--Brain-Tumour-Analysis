"use client";

import React, { useRef, useState, useCallback } from "react";
import JSZip from "jszip";
import { Upload, CheckCircle2, Loader2, AlertTriangle, X, FolderOpen } from "lucide-react";
import { MAX_FILE_SIZE_BYTES } from "@/lib/constants";
import type { Sequence } from "@/lib/constants";

export interface SequenceFile {
  sequence:     Sequence;
  file:         File;
  originalName: string;
  sizeBytes:    number;
  oversized:    boolean;
}

interface Props {
  sequence:  Sequence;
  value:     SequenceFile | null;
  onChange:  (file: SequenceFile | null) => void;
  disabled?: boolean;
}

type DropState = "idle" | "dragging" | "zipping" | "ready" | "oversized";

export default function SequenceDropzone({ sequence, value, onChange, disabled = false }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dropState,    setDropState   ] = useState<DropState>(value ? (value.oversized ? "oversized" : "ready") : "idle");
  const [zipProgress,  setZipProgress ] = useState(0);

  async function zipFiles(files: FileList | File[]): Promise<File> {
    const zip = new JSZip();
    Array.from(files).forEach(f => zip.file(f.name, f));
    const blob = await zip.generateAsync(
      { type: "blob", compression: "DEFLATE", compressionOptions: { level: 1 } },
      (meta) => setZipProgress(Math.round(meta.percent))
    );
    return new File([blob], `${sequence}.zip`, { type: "application/zip" });
  }

  const handleFiles = useCallback(async (files: FileList | File[]) => {
    if (disabled || !files || files.length === 0) return;
    setDropState("zipping"); setZipProgress(0);
    try {
      const zipped    = await zipFiles(files);
      const oversized = zipped.size > MAX_FILE_SIZE_BYTES;
      onChange({ sequence, file: zipped, originalName: files.length === 1 ? files[0].name : `${files.length} files`, sizeBytes: zipped.size, oversized });
      setDropState(oversized ? "oversized" : "ready");
    } catch { setDropState("idle"); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sequence, disabled, onChange]);

  function onDragOver(e: React.DragEvent) { e.preventDefault(); if (!disabled) setDropState("dragging"); }
  function onDragLeave() { if (!value) setDropState("idle"); }
  function onDrop(e: React.DragEvent) { e.preventDefault(); if (e.dataTransfer.files.length > 0) handleFiles(e.dataTransfer.files); }
  function clearFile(e: React.MouseEvent) {
    e.stopPropagation(); onChange(null); setDropState("idle"); setZipProgress(0);
    if (inputRef.current) inputRef.current.value = "";
  }

  const borderColor =
    dropState === "dragging"  ? "var(--blue)"  :
    dropState === "ready"     ? "var(--green)"  :
    dropState === "oversized" ? "var(--red)"    :
    dropState === "zipping"   ? "var(--amber)"  :
    "var(--border)";

  const bgColor =
    dropState === "dragging"  ? "var(--blue-dim)"  :
    dropState === "ready"     ? "var(--green-dim)"  :
    dropState === "oversized" ? "var(--red-dim)"    :
    dropState === "zipping"   ? "var(--amber-dim)"  :
    "var(--surface)";

  return (
    <div
      className={`relative rounded-xl border-2 transition-all duration-200 ${disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}`}
      style={{ borderColor, backgroundColor: bgColor }}
      onDragOver={onDragOver} onDragLeave={onDragLeave} onDrop={onDrop}
      onClick={() => !disabled && dropState !== "zipping" && inputRef.current?.click()}
    >
      <input
        ref={inputRef} type="file" accept=".dcm,.nii,.nii.gz,application/dicom" className="sr-only"
        onChange={(e) => e.target.files && handleFiles(e.target.files)}
        disabled={disabled || dropState === "zipping"}
      />
      <div className="p-4">
        <div className="flex items-center justify-between mb-3">
          <span
            className="text-[11px] font-bold uppercase tracking-widest font-mono px-2 py-0.5 rounded"
            style={{ color: borderColor, backgroundColor: borderColor + "22", border: `1px solid ${borderColor}44` }}
          >
            {sequence}
          </span>
          {(dropState === "ready" || dropState === "oversized") && (
            <button onClick={clearFile} className="transition-colors" style={{ color: "var(--muted)" }} aria-label="Remove file">
              <X size={13} />
            </button>
          )}
        </div>

        {(dropState === "idle" || dropState === "dragging") && (
          <div className="flex flex-col items-center gap-2 py-4 text-center">
            <FolderOpen size={22} style={{ color: dropState === "dragging" ? "var(--blue)" : "var(--muted)" }} />
            <p className="text-[12px] font-medium" style={{ color: dropState === "dragging" ? "var(--blue)" : "var(--muted)" }}>
              {dropState === "dragging" ? "Drop DICOM files here" : "Drop files or click to browse"}
            </p>
            <p className="text-[10px]" style={{ color: "var(--muted)", opacity: 0.6 }}>Max 500 MB after zipping</p>
          </div>
        )}

        {dropState === "zipping" && (
          <div className="py-4 space-y-2.5">
            <div className="flex items-center gap-2">
              <Loader2 size={14} className="animate-spin shrink-0" style={{ color: "var(--amber)" }} />
              <p className="text-[12px] font-medium" style={{ color: "var(--amber)" }}>Zipping files… {zipProgress}%</p>
            </div>
            <div className="w-full h-1.5 rounded-full overflow-hidden" style={{ backgroundColor: "var(--surface-2)" }}>
              <div className="h-full rounded-full transition-all duration-200" style={{ width: `${zipProgress}%`, backgroundColor: "var(--amber)" }} />
            </div>
          </div>
        )}

        {dropState === "ready" && value && (
          <div className="flex items-center gap-2.5 py-1">
            <CheckCircle2 size={16} className="shrink-0" style={{ color: "var(--green)" }} />
            <div className="min-w-0 flex-1">
              <p className="text-[12px] font-medium truncate" style={{ color: "var(--green)" }}>{value.originalName}</p>
              <p className="text-[10px] mt-0.5" style={{ color: "var(--muted)" }}>{(value.sizeBytes / 1024 / 1024).toFixed(1)} MB</p>
            </div>
          </div>
        )}

        {dropState === "oversized" && value && (
          <div className="flex items-start gap-2.5 py-1">
            <AlertTriangle size={15} className="shrink-0 mt-0.5" style={{ color: "var(--red)" }} />
            <div className="min-w-0 flex-1">
              <p className="text-[12px] font-medium" style={{ color: "var(--red)" }}>File too large</p>
              <p className="text-[10px] mt-0.5" style={{ color: "var(--muted)" }}>{(value.sizeBytes / 1024 / 1024).toFixed(0)} MB — limit is 500 MB</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
} 