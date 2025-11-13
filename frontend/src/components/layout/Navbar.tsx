import { Link } from 'react-router-dom';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/contexts/AuthContext';
import { useCart } from '@/contexts/CartContext';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet';
import { User, LogOut, Settings, Package, Menu, ShoppingBag, Users, Store, ShoppingCart } from 'lucide-react';

export function Navbar() {
  const { user, isAuthenticated, isVendor, logout } = useAuth();
  const { itemsCount } = useCart();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <nav className="border-b">
      <div className="container mx-auto px-4 py-3 md:py-4">
        {/* Mobile Layout */}
        <div className="flex md:hidden items-center justify-between">
          {/* Left: Hamburger Menu */}
          <Sheet open={mobileMenuOpen} onOpenChange={setMobileMenuOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" className="z-50">
                <Menu className="h-6 w-6" />
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="w-[280px]">
              <SheetHeader>
                <SheetTitle className="text-base">Menu</SheetTitle>
              </SheetHeader>
              <div className="flex flex-col gap-3 mt-6">
                <Link to="/products" onClick={() => setMobileMenuOpen(false)}>
                  <Button variant="ghost" className="w-full justify-start text-sm h-10">
                    <ShoppingBag className="mr-2 h-4 w-4" />
                    Products
                  </Button>
                </Link>
                <Link to="/buying-groups" onClick={() => setMobileMenuOpen(false)}>
                  <Button variant="ghost" className="w-full justify-start text-sm h-10">
                    <Users className="mr-2 h-4 w-4" />
                    Group Buying
                  </Button>
                </Link>
                <Link to="/vendors" onClick={() => setMobileMenuOpen(false)}>
                  <Button variant="ghost" className="w-full justify-start text-sm h-10">
                    <Store className="mr-2 h-4 w-4" />
                    Vendors
                  </Button>
                </Link>

                {isAuthenticated && (
                  <>
                    <div className="border-t my-2" />
                    {isVendor && (
                      <Link to="/vendors/dashboard" onClick={() => setMobileMenuOpen(false)}>
                        <Button variant="ghost" className="w-full justify-start text-sm h-10">
                          <Package className="mr-2 h-4 w-4" />
                          Vendor Dashboard
                        </Button>
                      </Link>
                    )}
                    <Link to="/profile" onClick={() => setMobileMenuOpen(false)}>
                      <Button variant="ghost" className="w-full justify-start text-sm h-10">
                        <Settings className="mr-2 h-4 w-4" />
                        Profile
                      </Button>
                    </Link>
                    <Link to="/orders" onClick={() => setMobileMenuOpen(false)}>
                      <Button variant="ghost" className="w-full justify-start text-sm h-10">
                        <Package className="mr-2 h-4 w-4" />
                        My Orders
                      </Button>
                    </Link>
                    <Button
                      variant="ghost"
                      className="w-full justify-start text-sm h-10 text-red-600 hover:text-red-700 hover:bg-red-50"
                      onClick={() => {
                        logout();
                        setMobileMenuOpen(false);
                      }}
                    >
                      <LogOut className="mr-2 h-4 w-4" />
                      Logout
                    </Button>
                  </>
                )}

                {!isAuthenticated && (
                  <>
                    <div className="border-t my-2" />
                    <Link to="/login" onClick={() => setMobileMenuOpen(false)}>
                      <Button variant="ghost" className="w-full text-sm h-10">Login</Button>
                    </Link>
                    <Link to="/register" onClick={() => setMobileMenuOpen(false)}>
                      <Button className="w-full text-sm h-10">Sign Up</Button>
                    </Link>
                  </>
                )}
              </div>
            </SheetContent>
          </Sheet>

          {/* Center: Logo */}
          <Link to="/" className="absolute left-1/2 transform -translate-x-1/2 text-lg font-bold">
            Provisions Link
          </Link>

          {/* Right: User Menu */}
          {isAuthenticated ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon">
                  <User className="h-5 w-5" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuLabel className="text-sm">
                  {user?.first_name || user?.email}
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <Link to="/profile">
                  <DropdownMenuItem className="text-sm">
                    <Settings className="mr-2 h-4 w-4" />
                    Profile
                  </DropdownMenuItem>
                </Link>
                <Link to="/orders">
                  <DropdownMenuItem className="text-sm">
                    <Package className="mr-2 h-4 w-4" />
                    My Orders
                  </DropdownMenuItem>
                </Link>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={logout} className="text-sm">
                  <LogOut className="mr-2 h-4 w-4" />
                  Logout
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          ) : (
            // Spacer to balance layout when user is not authenticated
            <div className="w-10" />
          )}
        </div>

        {/* Desktop Layout */}
        <div className="hidden md:flex items-center justify-between relative">
          {/* Left: Logo */}
          <Link to="/" className="flex items-center gap-2">
            <img src="/logo.svg" alt="Provisions Link" className="h-10 w-10" />
            <span className="text-2xl font-bold">Provisions Link</span>
          </Link>

          {/* Center: Navigation Links */}
          <div className="absolute left-1/2 transform -translate-x-1/2 flex items-center gap-4">
            <Link to="/products">
              <Button variant="ghost">Products</Button>
            </Link>
            <Link to="/buying-groups">
              <Button variant="ghost">Group Buying</Button>
            </Link>
            <Link to="/vendors">
              <Button variant="ghost">Vendors</Button>
            </Link>
          </div>

          {/* Right: User Actions */}
          <div className="flex items-center gap-4">
            {isAuthenticated ? (
              <>
                {/* Cart Icon with Badge */}
                <Link to="/cart" className="relative hover:text-primary transition-colors">
                  <ShoppingCart className="h-5 w-5" />
                  {itemsCount > 0 && (
                    <span className="absolute -top-2 -right-2 flex h-5 w-5 items-center justify-center rounded-full bg-primary text-xs text-primary-foreground font-medium">
                      {itemsCount}
                    </span>
                  )}
                </Link>

                {isVendor && (
                  <Link to="/vendors/dashboard">
                    <Button variant="outline">
                      <Package className="mr-2 h-4 w-4" />
                      Vendor Dashboard
                    </Button>
                  </Link>
                )}

                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon">
                      <User className="h-5 w-5" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuLabel>
                      {user?.first_name || user?.email}
                    </DropdownMenuLabel>
                    <DropdownMenuSeparator />
                    <Link to="/profile">
                      <DropdownMenuItem>
                        <Settings className="mr-2 h-4 w-4" />
                        Profile
                      </DropdownMenuItem>
                    </Link>
                    <Link to="/orders">
                      <DropdownMenuItem>
                        <Package className="mr-2 h-4 w-4" />
                        My Orders
                      </DropdownMenuItem>
                    </Link>
                    <Link to="/buying-groups/my-commitments">
                      <DropdownMenuItem>
                        <Users className="mr-2 h-4 w-4" />
                        My Commitments
                      </DropdownMenuItem>
                    </Link>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem onClick={logout}>
                      <LogOut className="mr-2 h-4 w-4" />
                      Logout
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </>
            ) : (
              <>
                <Link to="/login">
                  <Button variant="ghost">Login</Button>
                </Link>
                <Link to="/register">
                  <Button>Sign Up</Button>
                </Link>
              </>
            )}
          </div>
        </div>
      </div>
    </nav>
  );
}