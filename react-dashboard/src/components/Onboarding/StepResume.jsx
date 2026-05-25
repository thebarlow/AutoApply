import { useState } from "react";
import {
  uploadProfileResume,
  parseProfileResume,
  getProfiles,
  getProfile,
  createProfile,
  updateProfile,
  setActiveProfile,
} from "../../api";

const inputClass =
  "w-full bg-white/5 border border-space-border rounded-lg px-3 py-2 text-sm text-space-text placeholder-space-dim focus:outline-none focus:border-purple-500 transition-colors";

// Returns the full profile object (with nested data) for the active profile,
// creating one if none exist yet.
async function getOrCreateActiveProfile() {
  const { profiles, active_id } = await getProfiles();
  let profileId = null;

  if (active_id) {
    profileId = active_id;
  } else if (profiles && profiles.length > 0) {
    profileId = profiles[0].id;
    await setActiveProfile(profileId);
  } else {
    // No profiles at all — create a default one.
    const created = await createProfile("My Profile");
    profileId = created.id;
    await setActiveProfile(profileId);
  }

  // Fetch the full profile row (includes nested data object).
  return getProfile(profileId);
}

export default function StepResume({ onBack, onFinish }) {
  const [file, setFile] = useState(null);
  const [parsing, setParsing] = useState(false);
  const [parsed, setParsed] = useState(null); // { name, first_name, last_name, work_history, skills, education }
  const [error, setError] = useState("");

  const onParse = async () => {
    if (!file) return;
    setParsing(true);
    setError("");
    try {
      // Step 1: Upload the file to get its server-side path.
      const { path, filename } = await uploadProfileResume(file);

      // Step 2: Get or create the active profile.
      const profile = await getOrCreateActiveProfile();

      // Step 3: Associate the uploaded file with the profile so the parse
      //         endpoint can read it from disk. getProfile returns a flat object
      //         where top-level fields come from the row and profile data lives
      //         in a nested `data` key.
      const existingData = profile.data || {};
      await updateProfile(profile.id, {
        name: profile.name || "My Profile",
        data: {
          ...existingData,
          resume_path: path,
          resume_filename: filename,
          resume_uploaded_at: new Date().toISOString(),
        },
      });

      // Step 4: Parse the resume — this merges extracted fields (skills,
      //         work_history, education, etc.) back into the profile row so
      //         /api/setup-status returns resume_parsed: true.
      //         Returns { id, name } — the name may have been updated from the resume.
      const result = await parseProfileResume(profile.id);

      // Fetch the updated profile to build the preview card.
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
        <button
          onClick={onParse}
          disabled={!file || parsing}
          className="px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold transition-colors"
        >
          {parsing ? "Parsing…" : "Parse with AI"}
        </button>
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
      <div className="flex justify-between">
        <button
          onClick={onBack}
          className="px-4 py-2 rounded-lg border border-space-border text-sm text-space-dim hover:text-space-text transition-colors"
        >
          Back
        </button>
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
