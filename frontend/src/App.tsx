import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClientProvider } from '@tanstack/react-query';
import { queryClient } from './lib/queryClient';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { CartProvider } from './contexts/CartContext';
import { Layout } from './components/layout/Layout';
import { HomePage } from './pages/HomePage';
import { LoginPage } from './pages/LoginPage';
import { RegisterPage } from './pages/RegisterPage';
import { ProfilePage } from './pages/ProfilePage';
import { ProductsPage } from './pages/ProductsPage';
import { ProductDetailPage } from './pages/ProductDetailPage';
import BuyingGroupsPage from './pages/BuyingGroupsPage';
import BuyingGroupDetailPage from './pages/BuyingGroupDetailPage';
import MyCommitmentsPage from './pages/MyCommitmentsPage';
import CartPage from './pages/CartPage';
import CheckoutPage from './pages/CheckoutPage';
import PaymentPage from './pages/PaymentPage';
import OrdersPage from './pages/OrdersPage';
import OrderDetailPage from './pages/OrderDetailPage';
import VendorsPage from './pages/VendorsPage';
import VendorDetailPage from './pages/VendorDetailPage';
import VendorDashboardPage from './pages/VendorDashboardPage';
import VendorRegistrationPage from './pages/VendorRegistrationPage';
import AddressesPage from './pages/AddressesPage';
import AddAddressPage from './pages/AddAddressPage';
import EditAddressPage from './pages/EditAddressPage';
import { Toaster } from './components/ui/toaster';

// Protected Route wrapper
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return <div>Loading...</div>;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <CartProvider>
            <Routes>
              {/* All routes wrapped in Layout */}
              <Route path="/" element={<Layout />}>
                <Route index element={<HomePage />} />
                <Route path="login" element={<LoginPage />} />
                <Route path="register" element={<RegisterPage />} />
                
                {/* Profile route */}
                <Route path="profile" element={
                  <ProtectedRoute>
                    <ProfilePage />
                  </ProtectedRoute>
                } />
                
                {/* Address routes */}
                <Route path="addresses">
                  <Route index element={
                    <ProtectedRoute>
                      <AddressesPage />
                    </ProtectedRoute>
                  } />
                  <Route path="new" element={
                    <ProtectedRoute>
                      <AddAddressPage />
                    </ProtectedRoute>
                  } />
                  <Route path=":id/edit" element={
                    <ProtectedRoute>
                      <EditAddressPage />
                    </ProtectedRoute>
                  } />
                </Route>
                
                {/* Products routes */}
                <Route path="products">
                  <Route index element={<ProductsPage />} />
                  <Route path=":id" element={<ProductDetailPage />} />
                </Route>

                {/* Buying Groups routes */}
                <Route path="buying-groups">
                  <Route index element={<BuyingGroupsPage />} />
                  <Route path=":id" element={<BuyingGroupDetailPage />} />
                  <Route path="my-commitments" element={
                    <ProtectedRoute>
                      <MyCommitmentsPage />
                    </ProtectedRoute>
                  } />
                </Route>

                {/* Cart and Checkout routes */}
                <Route path="cart" element={
                  <ProtectedRoute>
                    <CartPage />
                  </ProtectedRoute>
                } />
                <Route path="checkout" element={
                  <ProtectedRoute>
                    <CheckoutPage />
                  </ProtectedRoute>
                } />
                <Route path="payment" element={
                  <ProtectedRoute>
                    <PaymentPage />
                  </ProtectedRoute>
                } />

                {/* Vendors routes */}
                <Route path="vendors">
                  <Route index element={<VendorsPage />} />
                  <Route path=":id" element={<VendorDetailPage />} />
                  <Route path="register" element={
                    <ProtectedRoute>
                      <VendorRegistrationPage />
                    </ProtectedRoute>
                  } />
                  <Route path="dashboard" element={
                    <ProtectedRoute>
                      <VendorDashboardPage />
                    </ProtectedRoute>
                  } />
                </Route>

                {/* Orders routes */}
                <Route path="orders">
                  <Route index element={
                    <ProtectedRoute>
                      <OrdersPage />
                    </ProtectedRoute>
                  } />
                  <Route path=":id" element={
                    <ProtectedRoute>
                      <OrderDetailPage />
                    </ProtectedRoute>
                  } />
                </Route>

                {/* 404 catch-all */}
                <Route path="*" element={<Navigate to="/" replace />} />
              </Route>
            </Routes>
            <Toaster />
          </CartProvider>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;