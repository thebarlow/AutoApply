export default function LoginScreen({ betaClosed }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-space-bg text-space-text">
      <div className="w-full max-w-sm text-center px-6">
        <h1 className="text-2xl font-bold mb-4">Auto Apply</h1>
        {betaClosed ? (
          <p className="text-red-400 text-sm mb-6">
            This is a closed beta. Your account isn't on the invite list yet —
            request access and check back soon.
          </p>
        ) : (
          <p className="text-space-dim text-sm mb-6">Sign in to continue.</p>
        )}
        <div className="flex flex-col gap-3">
          <a href="/auth/login/google">
            <button className="w-full py-2.5 rounded-lg border border-space-border bg-[#1a1a2e] hover:bg-[#23233a] text-space-text font-medium transition-colors">
              Sign in with Google
            </button>
          </a>
          <a href="/auth/login/github">
            <button className="w-full py-2.5 rounded-lg border border-space-border bg-[#1a1a2e] hover:bg-[#23233a] text-space-text font-medium transition-colors">
              Sign in with GitHub
            </button>
          </a>
        </div>
      </div>
    </div>
  )
}
