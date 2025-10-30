// frontend/src/components/orders/OrderItemsTable.tsx
// Table displaying order line items

import { OrderItem } from '@/types';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

interface OrderItemsTableProps {
  items: OrderItem[];
}

export function OrderItemsTable({ items }: OrderItemsTableProps) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-[50%]">Product</TableHead>
          <TableHead className="text-center">Quantity</TableHead>
          <TableHead className="text-right">Unit Price</TableHead>
          <TableHead className="text-right">Total</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((item) => (
          <TableRow key={item.id}>
            <TableCell>
              <div className="flex items-center gap-3">
                {item.product.primary_image && (
                  <img
                    src={item.product.primary_image}
                    alt={item.product.name}
                    className="w-12 h-12 object-cover rounded"
                  />
                )}
                <div>
                  <p className="font-medium">{item.product.name}</p>
                  <p className="text-sm text-muted-foreground">
                    {item.product.unit}
                  </p>
                  {parseFloat(item.discount_amount) > 0 && (
                    <p className="text-sm text-green-600">
                      Discount: £{parseFloat(item.discount_amount).toFixed(2)}
                    </p>
                  )}
                </div>
              </div>
            </TableCell>
            <TableCell className="text-center">{item.quantity}</TableCell>
            <TableCell className="text-right">
              £{parseFloat(item.unit_price).toFixed(2)}
            </TableCell>
            <TableCell className="text-right font-medium">
              £{parseFloat(item.total_price).toFixed(2)}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}