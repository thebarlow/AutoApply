import { CONTACT_EMAIL } from '../legal/links'

const oauthBtn =
  'w-full py-2.5 rounded-lg border border-space-border bg-[#1a1a2e] hover:bg-[#23233a] text-space-text font-medium transition-colors'

export default function SignInCard({ isAuthed, betaClosed }) {
  return (
    <section id="signin" className="w-full max-w-sm mx-auto text-center">
      {isAuthed ? (
        <a href="/">
          <button className="w-full py-2.5 rounded-lg bg-space-accent hover:bg-purple-500 text-white font-semibold transition-colors">
            Go to dashboard
          </button>
        </a>
      ) : (
        <>
          {/* `betaClosed` keeps its old name to match the ?beta=closed redirect
              wiring; it now means "the OAuth login was rejected" (unverified
              email or suspended account), not that signups are closed. */}
          {betaClosed ? (
            <p className="text-red-400 text-sm mb-6">
              We couldn't sign you in. Make sure the email on your Google
              account is verified. If your account was suspended, contact{' '}
              <span className="select-all text-red-300">{CONTACT_EMAIL}</span>.
            </p>
          ) : (
            <p className="text-space-dim text-sm mb-6">
              Anyone can sign up. It's free with your own AI API key, or you can
              buy credits.
            </p>
          )}
          <div className="flex flex-col gap-3">
            <a href="/auth/login/google">
              <button className={oauthBtn}>Sign in with Google</button>
            </a>
          </div>
          <p className="mt-4 text-xs text-space-dim">
            By signing in you agree to the{' '}
            <a href="/terms" className="underline hover:text-purple-400">Terms</a> and{' '}
            <a href="/privacy" className="underline hover:text-purple-400">Privacy Policy</a>.
          </p>
        </>
      )}
    </section>
  )
}
