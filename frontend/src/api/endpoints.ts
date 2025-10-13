import apiClient from './client';
import type {
  LoginCredentials,
  RegisterData,
  AuthResponse,
  User,
  Product,
  ProductDetail,
  BuyingGroup,
  BuyingGroupDetail,
  PaginatedResponse,
  Vendor,
  Order,
  Address,
} from '@/types';

// Auth endpoints
export const authApi = {
  login: (credentials: LoginCredentials) =>
    apiClient.post<AuthResponse>('/users/login/', credentials),

  register: (data: RegisterData) =>
    apiClient.post<AuthResponse>('/users/register/', data),

  getProfile: () =>
    apiClient.get<User>('/users/profile/'),

  updateProfile: (data: Partial<User>) =>
    apiClient.patch<{ user: User }>('/users/update_profile/', data),

  logout: (refreshToken: string) =>
    apiClient.post('/users/logout/', { refresh_token: refreshToken }),
};

// Products endpoints
export const productsApi = {
  list: (params?: any) =>
    apiClient.get<PaginatedResponse<Product>>('/products/', { params }),

  get: (id: number) =>
    apiClient.get<ProductDetail>(`/products/${id}/`),

  search: (data: any) =>
    apiClient.post<PaginatedResponse<Product>>('/products/search/', data),

  getGroupBuying: (id: number) =>
    apiClient.get<{ product: string; active_groups: BuyingGroup[] }>(
      `/products/${id}/group_buying/`
    ),
};

// Buying Groups endpoints
export const buyingGroupsApi = {
  list: (params?: any) =>
    apiClient.get<PaginatedResponse<BuyingGroup>>('/buying-groups/', { params }),

  get: (id: number) =>
    apiClient.get<BuyingGroupDetail>(`/buying-groups/${id}/`),

  nearby: (params: { postcode: string; radius_km?: number }) =>
    apiClient.get<PaginatedResponse<BuyingGroup>>('/buying-groups/nearby/', { params }),

  join: (id: number, data: { quantity: number; buyer_postcode: string }) =>
    apiClient.post(`/buying-groups/${id}/join/`, data),

  progress: (id: number) =>
    apiClient.get(`/buying-groups/${id}/progress/`),
};

// Vendors endpoints
export const vendorsApi = {
  list: (params?: any) =>
    apiClient.get<PaginatedResponse<Vendor>>('/vendors/', { params }),

  get: (id: number) =>
    apiClient.get<Vendor>(`/vendors/${id}/`),

  register: (data: any) =>
    apiClient.post('/vendors/register/', data),

  searchByLocation: (params: { postcode: string; radius_km?: number }) =>
    apiClient.get('/vendors/search_by_location/', { params }),
};

// Orders endpoints
export const ordersApi = {
  list: (params?: any) =>
    apiClient.get<PaginatedResponse<Order>>('/orders/', { params }),

  get: (id: number) =>
    apiClient.get<Order>(`/orders/${id}/`),

  create: (data: any) =>
    apiClient.post<Order>('/orders/', data),
};

// Addresses endpoints
export const addressesApi = {
  list: () =>
    apiClient.get<Address[]>('/addresses/'),

  get: (id: number) =>
    apiClient.get<Address>(`/addresses/${id}/`),

  create: (data: Omit<Address, 'id' | 'created_at'>) =>
    apiClient.post<Address>('/addresses/', data),

  update: (id: number, data: Partial<Address>) =>
    apiClient.patch<Address>(`/addresses/${id}/`, data),

  delete: (id: number) =>
    apiClient.delete(`/addresses/${id}/`),

  setDefault: (id: number) =>
    apiClient.post<{ address: Address }>(`/addresses/${id}/set_default/`),
};