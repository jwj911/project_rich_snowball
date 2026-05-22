import Link from 'next/link'

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-gray-950 text-white">
      <h1 className="text-4xl font-bold">404</h1>
      <p className="mt-2 text-slate-400">页面不存在</p>
      <Link href="/" className="mt-4 text-red-400 hover:underline">
        返回工作台
      </Link>
    </div>
  )
}
