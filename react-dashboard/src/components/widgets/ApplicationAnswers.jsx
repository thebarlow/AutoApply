const YES_NO = ["", "yes", "no"];
const DECLINE = "Decline to self-identify";
const EEO_OPTIONS = {
  gender: ["", "Male", "Female", "Non-binary", DECLINE],
  race_ethnicity: ["", "American Indian or Alaska Native", "Asian", "Black or African American",
    "Hispanic or Latino", "Native Hawaiian or Pacific Islander", "White", "Two or more races", DECLINE],
  veteran_status: ["", "I am a protected veteran", "I am not a protected veteran", DECLINE],
  disability_status: ["", "Yes, I have a disability", "No, I do not have a disability", DECLINE],
};
const EEO_LABELS = {
  gender: "Gender", race_ethnicity: "Race / Ethnicity",
  veteran_status: "Veteran status", disability_status: "Disability status",
};

export default function ApplicationAnswers({ value, onChange }) {
  const elig = value?.eligibility || {};
  const eeo = value?.eeo || {};
  const setElig = (k, v) => onChange({ eligibility: { ...elig, [k]: v }, eeo });
  const setEeo = (k, v) => onChange({ eligibility: elig, eeo: { ...eeo, [k]: v } });

  return (
    <div className="application-answers">
      <h4>Eligibility</h4>
      <label>Authorized to work (US)?
        <select value={elig.work_authorized || ""} onChange={(e) => setElig("work_authorized", e.target.value)}>
          {YES_NO.map((o) => <option key={o} value={o} style={{ color: "black" }}>{o || "—"}</option>)}
        </select>
      </label>
      <label>Require sponsorship?
        <select value={elig.requires_sponsorship || ""} onChange={(e) => setElig("requires_sponsorship", e.target.value)}>
          {YES_NO.map((o) => <option key={o} value={o} style={{ color: "black" }}>{o || "—"}</option>)}
        </select>
      </label>
      <label>Willing to relocate?
        <select value={elig.willing_to_relocate || ""} onChange={(e) => setElig("willing_to_relocate", e.target.value)}>
          {YES_NO.map((o) => <option key={o} value={o} style={{ color: "black" }}>{o || "—"}</option>)}
        </select>
      </label>
      <label>Earliest start date
        <input value={elig.start_date || ""} onChange={(e) => setElig("start_date", e.target.value)} />
      </label>
      <label>Years of experience
        <input value={elig.years_experience || ""} onChange={(e) => setElig("years_experience", e.target.value)} />
      </label>

      <h4>EEO self-identification (voluntary)</h4>
      {Object.keys(EEO_OPTIONS).map((k) => (
        <label key={k}>{EEO_LABELS[k]}
          <select value={eeo[k] || ""} onChange={(e) => setEeo(k, e.target.value)}>
            {EEO_OPTIONS[k].map((o) => <option key={o} value={o} style={{ color: "black" }}>{o || "—"}</option>)}
          </select>
        </label>
      ))}
    </div>
  );
}
