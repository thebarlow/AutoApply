import { motion } from 'framer-motion'

const containerVariants = {
  hidden: {},
  show: {
    transition: {
      staggerChildren: 0.1,
    },
  },
}

export default function Dashboard({ children }) {
  return (
    <motion.main
      variants={containerVariants}
      initial="hidden"
      animate="show"
      className="grid grid-cols-5 gap-4 p-6 h-[calc(100vh-53px)]"
    >
      {children}
    </motion.main>
  )
}
