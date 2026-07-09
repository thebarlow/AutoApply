import { useState } from "react";
import GatedButton from "../shared/GatedButton";
import Spinner from "../shared/Spinner";
import {
  uploadProfileResume,
  proposeParse,
  applyParse,
  getProfiles,
  getProfile,
  updateProfile,
} from "../../api";

export default function StepResume({ onFinish, onEdit }) {
  const [file, setFile] = useState(null);
  const [parsing, setParsing] = useState(false);
  const [error, setError] = useState("");
  const [sections, setSections] = useState(null);

  const onParse = async () => {
    if (!file) return;
    setParsing(true);
    setError("");
    try {
      // Upload the file to get its server-side path.
      const { path, filename } = await uploadProfileResume(file);

      // Resolve the already-provisioned active profile (no creation needed).
      const { profiles, active_id } = await getProfiles();
      const resolvedProfileId =
        active_id ?? (profiles && profiles[0] && profiles[0].id);
      if (!resolvedProfileId) throw new Error("No profile found for this account");

      // Attach the uploaded file to the profile so parse can read it.
      // Fetch the full profile (the list response omits `data`) so we merge
      // onto existing fields instead of wiping them.
      const profile = await getProfile(resolvedProfileId);
      const existingData = profile.data || {};
      await updateProfile(resolvedProfileId, {
        name: profile.name,
        data: {
          ...existingData,
          resume_path: path,
          resume_filename: filename,
          resume_uploaded_at: new Date().toISOString(),
        },
      });

      // Propose the parsed sections, then apply them as-is. Onboarding no longer
      // asks the user to triage sections here — they confirm and optionally jump
      // to the profile editor to refine. (Per-job tailoring lives in the editor.)
      const p = await proposeParse(resolvedProfileId);
      await applyParse(resolvedProfileId, p);
      setSections(p.sections.map((s) => s.name));
    } catch (e) {
      setError(e.message || "Parse failed");
    } finally {
      setParsing(false);
    }
  };

  if (sections) {
    return (
      <div>
        <h2 className="text-lg font-semibold mb-2">Resume parsed</h2>
        <p className="text-sm text-space-dim mb-4">
          Parsed the following sections:{" "}
          <span className="text-space-text">{sections.join(", ")}</span>
        </p>
        {error && (
          <div className="mb-4 px-3 py-2 rounded-lg border border-red-500/30 bg-red-500/10 text-sm text-red-400">
            {error}
          </div>
        )}
        <div className="flex gap-2 justify-end">
          <button
            onClick={onEdit}
            className="px-4 py-2 rounded-lg border border-space-border text-space-text hover:bg-white/10 text-sm font-semibold transition-colors"
          >
            Edit
          </button>
          <button
            onClick={onFinish}
            className="px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-sm font-semibold transition-colors"
          >
            OK
          </button>
        </div>
      </div>
    );
  }

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

    </div>
  );
}
