import { Outlet, Link } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { useCart } from '@/contexts/CartContext';
import { Navbar } from './Navbar';
import { ShoppingCart } from 'lucide-react';

export function Layout() {
  const { isAuthenticated } = useAuth();
  const { itemsCount } = useCart();

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Navbar */}
      <Navbar />

      {/* Cart Icon - Floating on mobile, integrated on desktop */}
      {isAuthenticated && itemsCount > 0 && (
        <Link
          to="/cart"
          className="fixed bottom-4 right-4 md:hidden z-40 flex h-14 w-14 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg hover:shadow-xl transition-shadow"
        >
          <ShoppingCart className="h-6 w-6" />
          <span className="absolute -top-1 -right-1 flex h-6 w-6 items-center justify-center rounded-full bg-red-500 text-xs text-white font-bold">
            {itemsCount}
          </span>
        </Link>
      )}

      {/* Main Content */}
      <main className="flex-1">
        <Outlet />
      </main>

      {/* Footer */}
      <footer className="border-t py-4">
        <div className="container mx-auto px-4 text-center text-xs text-muted-foreground">
          © 2025 Provisions Link. All rights reserved.
        </div>
      </footer>
    </div>
  );
}