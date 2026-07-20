const LABELS = {
  easy_apply: 'Easy Apply',
  greenhouse: 'Greenhouse',
  lever: 'Lever',
  ashby: 'Ashby',
  workday: 'Workday',
  icims: 'iCIMS',
  taleo: 'Taleo',
  smartrecruiters: 'SmartRecruiters',
  jobvite: 'Jobvite',
  bamboohr: 'BambooHR',
  other: 'External',
};

// Small chip summarizing how a job is applied to.
export default function AtsChip({ atsType, easyApply, atsDomain }) {
  let label;
  if (atsType && LABELS[atsType]) label = LABELS[atsType];
  else if (easyApply === false) label = 'Resolving…';
  else return null; // easyApply == null and no ats_type → no signal yet

  const title = atsType === 'other' && atsDomain ? atsDomain : undefined;
  return (
    <span
      title={title}
      className="text-[10px] px-1.5 py-0.5 rounded bg-space-mid text-space-dim shrink-0"
    >
      {label}
    </span>
  );
}
