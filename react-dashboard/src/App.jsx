import Navbar from './components/Navbar'
import Dashboard from './components/Dashboard'
import Pipeline from './components/widgets/Pipeline'
import Settings from './components/widgets/Settings'

export default function App() {
  return (
    <div className="min-h-screen text-space-text">
      <Navbar />
      <Dashboard>
        <div className="col-span-3 overflow-hidden h-full">
          <Pipeline />
        </div>
        <div className="col-span-2 overflow-hidden h-full">
          <Settings />
        </div>
      </Dashboard>
    </div>
  )
}
