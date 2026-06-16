import { useState } from "react";
import GatedButton from "../shared/GatedButton";
import Spinner from "../shared/Spinner";
import {
  uploadProfileResume,
  parseProfileResume,
  getProfiles,
  getProfile,
  updateProfile,
} from "../../api";

const inputClass =
  "w-full bg-white/5 border border-space-border rounded-lg px-3 py-2 text-sm text-space-text placeholder-space-dim focus:outline-none focus:border-purple-500 transition-colors";

export default function StepResume({ onFinish }) {
  const [file, setFile] = useState(null);
  const [parsing, setParsing] = useState(false);
  const [parsed, setParsed] = useState(null); // { name, first_name, last_name, work_history, skills, education }
  const [error, setError] = useState("");

  const onParse = async () => {
    if (!file) return;
    setParsing(true);
    setError("");
    try {
      // Upload the file to get its server-side path.
      const { path, filename } = await uploadProfileResume(file);

      // Resolve the already-provisioned active profile (no creation needed).
      const { profiles, active_id } = await getProfiles();
      const profileId =
        active_id ?? (profiles && profiles[0] && profiles[0].id);
      if (!profileId) throw new Error("No profile found for this account");

      // Attach the uploaded file to the profile so parse can read it.
      const profile = await getProfile(profileId);
      const existingData = profile.data || {};
      await updateProfile(profileId, {
        name: profile.name,
        data: {
          ...existingData,
          resume_path: path,
          resume_filename: filename,
          resume_uploaded_at: new Date().toISOString(),
        },
      });

      // Parse — merges skills/work_history/education into the profile row,
      // which flips /api/setup-status resume_parsed to true.
      const result = await parseProfileResume(profileId);

      const updated = await getProfile(result.id);
      const d = updated.data || {};
      setParsed({
        name: [d.first_name, d.last_name].filter(Boolean).join(" ") || result.name,
        email: d.email || "",
        topRole: d.work_history?.[0]?.title || "",
      });
    } catch (e) {
      setError(e.message || "Parse failed");
    } finally {
      setParsing(false);
    }
  };

  return (
    <div>
      <h2 className="text-lg font-semibold mb-2">Upload your resume</h2>
      <p className="text-sm text-space-dim mb-5">
        The app will parse your resume into structured fields using AI. You can
        edit anything afterwards in the Profile tab.
      </p>

      {/* File picker */}
      <div className="mb-4">
        <label className="text-xs text-space-dim block mb-1">
          Resume file <span className="text-red-400">*</span>
        </label>
        <input
          type="file"
          accept=".pdf,.md"
          className="block w-full text-sm text-space-dim file:mr-3 file:py-1.5 file:px-3 file:rounded file:border file:border-space-border file:bg-white/5 file:text-space-dim file:text-xs file:cursor-pointer hover:file:border-purple-500/50 transition-colors"
          onChange={(e) => {
            setFile(e.target.files?.[0] || null);
            setParsed(null);
            setError("");
          }}
        />
        <p className="text-xs text-space-dim mt-1">Accepts .pdf or .md</p>
      </div>

      {/* Parse button */}
      <div className="mb-5">
        <GatedButton
          action="parse_resume"
          onClick={onParse}
          disabled={!file || parsing}
          className="px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold transition-colors flex items-center gap-2"
        >
          {parsing ? <><Spinner /> <span>Parsing…</span></> : "Parse with AI"}
        </GatedButton>
        {parsing && (
          <p className="text-xs text-space-dim mt-2">
            This may take a few seconds…
          </p>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 px-3 py-2 rounded-lg border border-red-500/30 bg-red-500/10 text-sm text-red-400">
          {error}
        </div>
      )}

      {/* Parsed preview */}
      {parsed && (
        <div className="mb-5 px-3 py-3 rounded-lg border border-space-border bg-white/[0.03] text-sm flex flex-col gap-1.5">
          <p className="text-xs font-semibold uppercase tracking-widest text-space-dim mb-1">
            Parsed
          </p>
          <div>
            <span className="text-space-dim text-xs">Name: </span>
            <span className="text-space-text text-xs">{parsed.name || "—"}</span>
          </div>
          <div>
            <span className="text-space-dim text-xs">Email: </span>
            <span className="text-space-text text-xs">{parsed.email || "—"}</span>
          </div>
          <div>
            <span className="text-space-dim text-xs">Most recent role: </span>
            <span className="text-space-text text-xs">{parsed.topRole || "—"}</span>
          </div>
          <p className="text-xs text-emerald-400 mt-1">
            ✓ Resume data saved to your profile
          </p>
        </div>
      )}

      {/* Navigation */}
      <div className="flex justify-end">
        <button
          onClick={onFinish}
          disabled={!parsed}
          className="px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold transition-colors"
        >
          Finish
        </button>
      </div>
      {!parsed && (
        <p className="text-xs text-space-dim mt-2 text-center">
          Parse your resume first to continue.
        </p>
      )}
    </div>
  );
}
