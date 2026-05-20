import Navbar from './components/Navbar'
import Dashboard from './components/Dashboard'

export default function App() {
  return (
    <div className="min-h-screen text-space-text">
      <Navbar />
      <Dashboard>
        {/* Left column: 3/5 = 60% */}
        <div className="col-span-3 flex flex-col gap-4">
          <div className="bg-purple-900/20 rounded-xl flex-1 flex items-center justify-center text-space-dim">Inbox</div>
          <div className="bg-purple-900/20 rounded-xl flex-1 flex items-center justify-center text-space-dim">Processing</div>
          <div className="bg-purple-900/20 rounded-xl flex-1 flex items-center justify-center text-space-dim">Outbox</div>
        </div>
        {/* Right column: 2/5 = 40% */}
        <div className="col-span-2 flex flex-col gap-4">
          <div className="bg-blue-900/20 rounded-xl flex-1 flex items-center justify-center text-space-dim">Stats</div>
          <div className="bg-blue-900/20 rounded-xl flex-1 flex items-center justify-center text-space-dim">Settings</div>
        </div>
      </Dashboard>
    </div>
  )
}
