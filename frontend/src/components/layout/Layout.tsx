import { Outlet, Link } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { useCart } from '@/contexts/CartContext';
import { Button } from '@/components/ui/button';
import { ShoppingCart, User, LogOut, Package, Users } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

export function Layout() {
  const { isAuthenticated, user, logout } = useAuth();
  const { itemsCount } = useCart();

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Navbar */}
      <nav className="border-b">
        <div className="container mx-auto px-4">
          <div className="flex h-16 items-center justify-between">
            {/* Logo */}
            <Link to="/" className="flex items-center gap-2">
              <Package className="h-6 w-6 text-primary" />
              <span className="text-xl font-bold">Provisions Link</span>
            </Link>

            {/* Navigation Links */}
            <div className="hidden md:flex items-center gap-6">
              <Link 
                to="/products" 
                className="text-sm font-medium hover:text-primary transition-colors"
              >
                Products
              </Link>
              <Link 
                to="/buying-groups" 
                className="text-sm font-medium hover:text-primary transition-colors flex items-center gap-1"
              >
                <Users className="h-4 w-4" />
                Group Buys
              </Link>
              <Link 
                to="/vendors" 
                className="text-sm font-medium hover:text-primary transition-colors"
              >
                Vendors
              </Link>
            </div>

            {/* Right Side - Cart & User */}
            <div className="flex items-center gap-4">
              {isAuthenticated && (
                <>
                  {/* Cart Icon with Badge */}
                  <Link 
                    to="/cart" 
                    className="relative hover:text-primary transition-colors"
                  >
                    <ShoppingCart className="h-5 w-5" />
                    {itemsCount > 0 && (
                      <span className="absolute -top-2 -right-2 flex h-5 w-5 items-center justify-center rounded-full bg-primary text-xs text-primary-foreground font-medium">
                        {itemsCount}
                      </span>
                    )}
                  </Link>

                  {/* User Menu */}
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="icon">
                        <User className="h-5 w-5" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="w-56">
                      <div className="flex items-center justify-start gap-2 p-2">
                        <div className="flex flex-col space-y-1">
                          <p className="text-sm font-medium">
                            {user?.first_name} {user?.last_name}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {user?.email}
                          </p>
                        </div>
                      </div>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem asChild>
                        <Link to="/profile" className="cursor-pointer">
                          <User className="mr-2 h-4 w-4" />
                          Profile
                        </Link>
                      </DropdownMenuItem>
                      <DropdownMenuItem asChild>
                        <Link to="/orders" className="cursor-pointer">
                          <Package className="mr-2 h-4 w-4" />
                          My Orders
                        </Link>
                      </DropdownMenuItem>
                      <DropdownMenuItem asChild>
                        <Link to="/buying-groups/my-commitments" className="cursor-pointer">
                          <Users className="mr-2 h-4 w-4" />
                          My Commitments
                        </Link>
                      </DropdownMenuItem>
                      {user?.has_vendor_account && (
                        <>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem asChild>
                            <Link to="/vendors/dashboard" className="cursor-pointer">
                              Vendor Dashboard
                            </Link>
                          </DropdownMenuItem>
                        </>
                      )}
                      <DropdownMenuSeparator />
                      <DropdownMenuItem 
                        onClick={logout}
                        className="cursor-pointer text-red-600"
                      >
                        <LogOut className="mr-2 h-4 w-4" />
                        Logout
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </>
              )}

              {!isAuthenticated && (
                <div className="flex items-center gap-2">
                  <Button variant="ghost" asChild>
                    <Link to="/login">Login</Link>
                  </Button>
                  <Button asChild>
                    <Link to="/register">Sign Up</Link>
                  </Button>
                </div>
              )}
            </div>
          </div>
        </div>
      </nav>

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