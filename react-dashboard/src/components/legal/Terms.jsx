import LegalPage, { Section, List, Email } from './LegalPage'

export default function Terms() {
  return (
    <LegalPage title="Terms of Service">
      <p>
        These terms cover your use of AutoApply, a job-application tool built and run by
        Matthew Barlow as an individual. By signing in, you agree to them. They're short on
        purpose; please read them.
      </p>

      <Section title="The service">
        <p>
          AutoApply collects job postings, scores them against your background, and uses AI to
          generate tailored résumés and cover letters. It is a solo-developer project. Features
          may change, break, or be removed, and the service may be unavailable at times.
        </p>
      </Section>

      <Section title="Your account">
        <p>
          You sign in with a Google or GitHub account and are responsible for what happens under
          your account. Keep the information you give AutoApply accurate. Your use of the
          service is also covered by the <a href="/privacy" className="text-purple-300 hover:text-purple-200 underline">Privacy Policy</a>.
        </p>
      </Section>

      <Section title="AI-generated documents are drafts">
        <p>
          AI output can be wrong. It can misstate your experience, invent details, or miss what
          an employer is asking for. You are responsible for reviewing and correcting every
          résumé, cover letter, and form answer before you send or submit it. Only submit
          documents that truthfully describe you.
        </p>
      </Section>

      <Section title="No guarantee of results">
        <p>
          AutoApply does not guarantee interviews, job offers, or any other outcome. Job scores
          and skill matches are estimates to help you prioritize, not predictions.
        </p>
      </Section>

      <Section title="Your content">
        <p>
          You own the profile data, résumés, and documents in your account. You give AutoApply
          permission to store and process that content, including sending it to AI providers,
          only so the service can work for you. Only upload content you have the right to use.
        </p>
      </Section>

      <Section title="Job sites and the browser extension">
        <p>
          The browser extension works on LinkedIn, Indeed, and some application systems
          (Greenhouse, Lever, Ashby) when you use it. You are responsible for following those
          sites' terms of use. AutoApply is not affiliated with or endorsed by any of them.
        </p>
      </Section>

      <Section title="Credits and payments">
        <List>
          <li>
            AI actions on the platform's key use prepaid credits. Credits are bought through
            Stripe Checkout and have no cash value.
          </li>
          <li>
            Credit purchases are non-refundable, except where the law requires a refund. If
            something went wrong with a purchase, email <Email /> and it will be looked at.
          </li>
          <li>Prices in credits per action may change; the current prices are shown in the app.</li>
          <li>
            If an AI action fails, its credits are returned to your balance automatically.
          </li>
        </List>
      </Section>

      <Section title="Using your own API key">
        <p>
          If you add your own AI provider API key, AutoApply is free to use with it, and no
          credits are charged. Requests made with your key are billed to you by your provider
          under its terms, and you are responsible for those charges and for keeping the key
          within your provider's limits.
        </p>
      </Section>

      <Section title="Acceptable use">
        <p>Don't use AutoApply to:</p>
        <List>
          <li>break the law or anyone else's rights, or impersonate someone else</li>
          <li>submit false or misleading applications</li>
          <li>attack, overload, or try to get around the security or billing of the service</li>
          <li>access other users' data, or resell or automate access to the service at scale</li>
        </List>
        <p>
          Accounts that abuse the service may be suspended or closed, with or without notice.
        </p>
      </Section>

      <Section title="Provided as-is">
        <p>
          AutoApply is provided "as is" and "as available", without warranties of any kind. To
          the extent the law allows, Matthew Barlow is not liable for indirect or consequential
          losses arising from your use of the service, including missed opportunities or errors
          in generated documents.
        </p>
      </Section>

      <Section title="Ending your use">
        <p>
          You can stop using AutoApply at any time. To have your account and data deleted, email
          {' '}<Email />. The service may be discontinued; if that happens, there will be
          reasonable notice where possible.
        </p>
      </Section>

      <Section title="Changes to these terms">
        <p>
          If these terms change, the new version will be posted here with a new effective date.
          Continuing to use AutoApply after that means you accept the updated terms.
        </p>
      </Section>

      <Section title="Contact">
        <p>
          Questions about these terms: <Email />.
        </p>
      </Section>
    </LegalPage>
  )
}
