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
          {betaClosed ? (
            <p className="text-red-400 text-sm mb-6">
              This is a closed beta. Your account isn't on the invite list yet —
              request access and check back soon.
            </p>
          ) : (
            <p className="text-space-dim text-sm mb-6">Sign in to get started.</p>
          )}
          <div className="flex flex-col gap-3">
            <a href="/auth/login/google">
              <button className={oauthBtn}>Sign in with Google</button>
            </a>
            <a href="/auth/login/github">
              <button className={oauthBtn}>Sign in with GitHub</button>
            </a>
          </div>
        </>
      )}
    </section>
  )
}
