import QuoteCard from '@/components/market/QuoteCard'
import { Product } from '@/lib/api'

interface QuoteMobileListProps {
  products: Product[]
}

export default function QuoteMobileList({ products }: QuoteMobileListProps) {
  return (
    <div className="grid gap-3">
      {products.map((product) => (
        <QuoteCard key={product.id} product={product} />
      ))}
    </div>
  )
}
