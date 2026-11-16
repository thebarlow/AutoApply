import LegalPage, { Section, List, Email } from './LegalPage'

export default function Privacy() {
  return (
    <LegalPage title="Privacy Policy">
      <p>
        AutoApply helps you collect job postings, score them against your background, and
        generate tailored résumés and cover letters. This page explains, in plain terms, what
        data the service keeps, why, and who else touches it.
      </p>

      <Section title="Who runs AutoApply">
        <p>
          AutoApply is a personal project built and operated by Matthew Barlow, an individual
          developer, not a company. If you have a question about your data, email <Email />.
        </p>
      </Section>

      <Section title="What we collect">
        <List>
          <li>
            <strong className="text-white">Sign-in details.</strong> You sign in with Google. We
            store your email address and the account ID Google gives us. We never see or store a password.
          </li>
          <li>
            <strong className="text-white">Your profile and résumé.</strong> The résumé files
            you upload and the profile data parsed from them or typed in by you (work history,
            education, skills, contact links, and so on).
          </li>
          <li>
            <strong className="text-white">Application answers (optional).</strong> If you fill
            them in, eligibility answers and voluntary self-identification answers used to fill
            out job application forms. Every one of these is optional.
          </li>
          <li>
            <strong className="text-white">Job postings.</strong> Postings you add manually,
            through Find Jobs, or with the browser extension, plus their scores and skill
            matches.
          </li>
          <li>
            <strong className="text-white">Generated documents.</strong> The résumés and cover
            letters generated for you, your edits and feedback on them, and the prompt templates
            in your account.
          </li>
          <li>
            <strong className="text-white">Account records.</strong> Your credit balance and
            usage history, purchase records, and, if you add one, your own AI provider API key
            (stored encrypted; see below).
          </li>
        </List>
        <p>We use this data only to run the service for you. We don't sell it or use it for ads.</p>
      </Section>

      <Section title="AI processing">
        <p>
          Scoring jobs, parsing résumés, and generating documents means sending the relevant
          content (your profile, the job posting, and the prompt) to a large language model
          provider.
        </p>
        <List>
          <li>
            By default this goes through the platform's provider, OpenRouter, which routes the
            request to the underlying model. Their privacy terms apply to that processing.
          </li>
          <li>
            If you save your own API key, your content goes to the provider you picked
            (OpenRouter, OpenAI, Anthropic, or Google Gemini) under your own account with them,
            and that provider's terms apply.
          </li>
        </List>
        <p>
          Your API key is encrypted before it is stored. After you save it, the app only ever
          shows its last four characters, and it is used only to make requests on your behalf.
        </p>
      </Section>

      <Section title="Payments">
        <p>
          Credit purchases go through Stripe Checkout. Your card details are entered on Stripe's
          page and never reach AutoApply. We keep your Stripe customer ID and a record of each
          purchase (date, amount, credits) so your balance and purchase history are correct.
        </p>
      </Section>

      <Section title="Email">
        <p>
          Invitation emails and any other account emails are sent through Resend, which receives
          the recipient address and the message content. We don't send marketing email.
        </p>
      </Section>

      <Section title="The browser extension">
        <p>
          The optional extension adds a Scrape button to job listings on LinkedIn and Indeed.
          When you click it, the extension reads that posting (title, company, location,
          description, apply link) and sends it to your AutoApply account. It may open a
          background tab to follow a posting's external apply link to find which application
          system it uses, then closes that tab.
        </p>
        <p>
          On supported application pages (Greenhouse, Lever, Ashby), it reads the form's field
          labels so the app can work out which of your details belong in which field, and can
          fill those fields in for you to review. It does not submit applications on its own.
        </p>
        <p>
          The extension signs in with the same Google account and keeps a sign-in
          token in your browser's extension storage. We store only a hashed copy of that token,
          and you can sign out of the extension to revoke it.
        </p>
      </Section>

      <Section title="Error logs">
        <p>
          When something breaks, the server records the error along with request details (the
          route, request method, a request ID, and your account email and profile ID). These
          logs help fix bugs, are visible only to the administrator, and are kept for about 30 days.
          The administrator can also clear them at any time.
        </p>
      </Section>

      <Section title="Cookies and tracking">
        <p>
          AutoApply sets one cookie: a signed session cookie that keeps you logged in. It is
          strictly necessary for the site to work. There are no advertising trackers, analytics
          scripts, or third-party cookies.
        </p>
        <p>
          The Find Jobs page remembers which results you dismissed in your browser's local
          storage. That stays on your device.
        </p>
      </Section>

      <Section title="Where your data is stored and who else handles it">
        <p>
          The app and its database are hosted on Railway in the United States. The only other
          services that handle your data are the ones named above:
        </p>
        <List>
          <li>Google, for sign-in</li>
          <li>OpenRouter, or the AI provider for your own key, for AI processing</li>
          <li>Stripe, for payments</li>
          <li>Resend, for email</li>
          <li>Railway, for hosting</li>
        </List>
      </Section>

      <Section title="How long we keep data">
        <p>
          Your account data is kept while your account exists. Jobs you delete in the app are
          permanently removed within a day. Error logs are kept for about 30 days. Purchase
          records may be kept longer where tax or accounting rules require it.
        </p>
      </Section>

      <Section title="Deleting or exporting your data">
        <p>
          There isn't a self-serve delete or export button yet. Email <Email /> from the address
          you sign in with and ask for your data to be exported or your account and its data to
          be deleted, and it will be done.
        </p>
      </Section>

      <Section title="Changes to this policy">
        <p>
          If this policy changes, the updated version will be posted here with a new effective
          date.
        </p>
      </Section>

      <Section title="Contact">
        <p>
          Questions or requests: <Email />.
        </p>
      </Section>
    </LegalPage>
  )
}
