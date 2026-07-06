// react-joyride step configs. `openEvent` is a custom field (not read by
// joyride) that TourController dispatches to open the relevant panel/modal
// before the step is shown.

export const PART1_STEPS = [
  {
    target: '[data-tour="profile-tree"]',
    content:
      "Here's your profile, built from your résumé. Take a moment to check that everything parsed correctly.",
    placement: 'right',
    disableBeacon: true,
    openEvent: 'auto-apply:edit-profile',
  },
  {
    target: '[data-tour="profile-section"]',
    content:
      'Your résumé is a tree of sections — Experience, Education, Skills, and more. Rename, reorder, add, or remove them however you like.',
    placement: 'right',
    disableBeacon: true,
  },
  {
    target: '[data-tour="section-lock"]',
    content:
      'Lock a section to keep its wording exactly as written, or hide it from generated documents.',
    placement: 'right',
    disableBeacon: true,
  },
  {
    target: '[data-tour="section-prompt"]',
    content:
      'Give a section or item a prompt to steer how the AI writes it — the baseline facts, what to emphasize, and what never to claim.',
    placement: 'right',
    disableBeacon: true,
  },
  {
    target: '[data-tour="output-format"]',
    content:
      'Choose bullet points or paragraphs per field, and pick a résumé theme that suits you.',
    placement: 'right',
    disableBeacon: true,
  },
  {
    target: '[data-tour="job-inbox"]',
    content:
      "This is your job inbox — where every job you're working lives. It's empty right now, so let's add one.",
    placement: 'left',
    disableBeacon: true,
  },
  {
    target: '[data-tour="add-job"]',
    content:
      'Click here to paste a job posting and add it manually. Go ahead and add your first job — the tour picks back up once you do.',
    placement: 'bottom',
    disableBeacon: true,
  },
]

export const PART2_STEPS = [
  {
    target: '[data-tour="job-score"]',
    content:
      'Nice — your job is in. Each job is automatically scored against your profile so you know if it’s worth pursuing.',
    placement: 'left',
    disableBeacon: true,
  },
  {
    target: '[data-tour="generate"]',
    content:
      'Click here to generate a résumé and cover letter tailored to this specific job.',
    placement: 'left',
    disableBeacon: true,
  },
  {
    target: '[data-tour="document-preview"]',
    content:
      'Review, edit, and refine your documents here, with a live PDF preview side-by-side.',
    placement: 'left',
    disableBeacon: true,
    openEvent: 'auto-apply:open-document',
  },
  {
    target: '[data-tour="credit-balance"]',
    content:
      'Generating documents costs credits. Here’s your balance — and where to buy more when you run low. That’s the tour!',
    placement: 'bottom',
    disableBeacon: true,
  },
]
