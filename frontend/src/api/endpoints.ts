import apiClient from './client';
import type {
  LoginCredentials,
  RegisterData,
  AuthResponse,
  User,
  Product,
  BuyingGroup,
  BuyingGroupDetail,
  PaginatedResponse,
  ApiResponse,
  Vendor,
  Order,
  OrderDetail,
  Address,
  GroupCommitment,
  Cart,
  CartItem,
  CartSummaryResponse,
  CheckoutRequest,
  CheckoutResponse,
} from '@/types';

// Vendor Registration Types
export interface VendorRegistrationData {
  business_name: string;
  description: string;
  postcode: string;
  phone_number?: string;
  delivery_radius_km: number;
  min_order_value: number;
  vat_number?: string;
  logo_url?: string;
}

export interface VendorRegistrationResponse {
  vendor: Vendor;
  onboarding_url?: string;
  fsa_verified: boolean;
  message: string;
}

// Auth endpoints
export const authApi = {
  login: async (credentials: LoginCredentials): Promise<ApiResponse<AuthResponse>> => {
    const { data } = await apiClient.post<AuthResponse>('/users/login/', credentials);
    return { data };
  },

  register: async (data: RegisterData): Promise<ApiResponse<AuthResponse>> => {
    const { data: response } = await apiClient.post<AuthResponse>('/users/register/', data);
    return { data: response };
  },

  getProfile: async (): Promise<ApiResponse<User>> => {
    const { data } = await apiClient.get<User>('/users/profile/');
    return { data };
  },

  // FIXED: Return type now includes both message and user
  updateProfile: async (data: Partial<User>): Promise<ApiResponse<{ message: string; user: User }>> => {
    const { data: response } = await apiClient.patch<{ message: string; user: User }>(
      '/users/update_profile/',
      data
    );
    return { data: response };
  },

  // Change password endpoint
  changePassword: async (data: {
    old_password: string;
    new_password: string;
    new_password_confirm: string;
  }): Promise<ApiResponse<{ message: string; tokens: { access: string; refresh: string } }>> => {
    const { data: response } = await apiClient.post<{ message: string; tokens: { access: string; refresh: string } }>(
      '/users/change_password/',
      data
    );
    return { data: response };
  },

  logout: async (refreshToken: string): Promise<ApiResponse<{ message: string }>> => {
    const { data } = await apiClient.post<{ message: string }>('/users/logout/', { refresh_token: refreshToken });
    return { data };
  },

  deleteAccount: async (password: string): Promise<ApiResponse<{ message: string }>> => {
    const { data } = await apiClient.post<{ message: string }>('/users/delete_account/', { 
      password 
    });
    return { data };
  },
};

// Products endpoints
export const productsApi = {
  list: async (params?: { 
    page?: number; 
    search?: string; 
    page_size?: number;
    category?: number;
    vendor?: number;
  }): Promise<ApiResponse<PaginatedResponse<Product>>> => {
    const { data } = await apiClient.get<PaginatedResponse<Product>>('/products/', { params });
    return { data };
  },

  get: async (id: number): Promise<ApiResponse<Product>> => {
    const { data } = await apiClient.get<Product>(`/products/${id}/`);
    return { data };
  },

  search: async (searchData: any): Promise<ApiResponse<PaginatedResponse<Product>>> => {
    const { data } = await apiClient.post<PaginatedResponse<Product>>('/products/search/', searchData);
    return { data };
  },

  getGroupBuying: async (id: number): Promise<ApiResponse<{ product: string; active_groups: BuyingGroup[] }>> => {
    const { data } = await apiClient.get<{ product: string; active_groups: BuyingGroup[] }>(
      `/products/${id}/group_buying/`
    );
    return { data };
  },

  lowStock: async (params?: { vendor?: number }): Promise<ApiResponse<any>> => {
    const { data } = await apiClient.get('/products/low_stock/', { params });
    return { data };
  },

  uploadImage: async (id: number, imageFile: File): Promise<ApiResponse<{
    message: string;
    image_url: string;
  }>> => {
    const formData = new FormData();
    formData.append('primary_image', imageFile);

    const { data } = await apiClient.post<{ message: string; image_url: string }>(
      `/products/${id}/upload-image/`,
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    );
    return { data };
  },

  deleteImage: async (id: number): Promise<ApiResponse<{ message: string }>> => {
    const { data } = await apiClient.delete<{ message: string }>(
      `/products/${id}/delete-image/`
    );
    return { data };
  },
};

// Buying Groups endpoints 
export const buyingGroupsApi = {
  list: async (params?: { 
    page?: number; 
    status?: string;
    product?: number;
    hide_expired?: boolean;
  }): Promise<ApiResponse<PaginatedResponse<BuyingGroup>>> => {
    const { data } = await apiClient.get<PaginatedResponse<BuyingGroup>>('/buying-groups/', { params });
    return { data };
  },

  get: async (id: number): Promise<ApiResponse<BuyingGroupDetail>> => {
    const { data } = await apiClient.get<BuyingGroupDetail>(`/buying-groups/${id}/`);
    return { data };
  },

  nearMe: async (params: { 
    postcode: string; 
    radius?: number;
  }): Promise<ApiResponse<{ count: number; location: string; radius_km: number; groups: BuyingGroup[] }>> => {
    const { data } = await apiClient.get('/buying-groups/near_me/', { params });
    return { data };
  },

  activeGroups: async (): Promise<ApiResponse<{ count: number; groups: BuyingGroup[] }>> => {
    const { data } = await apiClient.get('/buying-groups/active_groups/');
    return { data };
  },

  commit: async (
    id: number, 
    commitmentData: { 
      quantity: number; 
      postcode: string;
      delivery_address_id: number;
      delivery_notes?: string;
    }
  ): Promise<ApiResponse<{
    message: string;
    commitment: GroupCommitment;
    payment_intent?: {
      client_secret: string | null;
      intent_id: string | null;
    };
    group_progress: number;
  }>> => {
    const { data } = await apiClient.post(`/buying-groups/${id}/commit/`, commitmentData);
    return { data };
  },

  validateAddress: async (
    groupId: number, 
    addressId: number
  ): Promise<ApiResponse<{
    valid: boolean;
    distance_km: number;
    max_distance_km: number;
    message: string;
  }>> => {
    const { data } = await apiClient.post(`/buying-groups/${groupId}/validate_address/`, {
      address_id: addressId,
    });
    return { data };
  },

  cancelCommitment: async (id: number): Promise<ApiResponse<{
    message: string;
    refunded_quantity: number;
  }>> => {
    const { data } = await apiClient.post(`/buying-groups/${id}/cancel_commitment/`);
    return { data };
  },

  myCommitments: async (): Promise<ApiResponse<{
    active: GroupCommitment[];
    confirmed: GroupCommitment[];
    cancelled: GroupCommitment[];
    total_count: number;
  }>> => {
    const { data } = await apiClient.get('/buying-groups/my_commitments/');
    return { data };
  },

  realtimeStatus: async (id: number): Promise<ApiResponse<{
    group: BuyingGroupRealtimeStatus;
    recent_updates: GroupUpdate[];
  }>> => {
    const { data } = await apiClient.get(`/buying-groups/${id}/realtime_status/`);
    return { data };
  },

  createGroup: async (groupData: {
    product_id: number;
    postcode: string;
    target_quantity?: number;
    discount_percent?: number;
    duration_days?: number;
    radius_km?: number;
  }): Promise<ApiResponse<BuyingGroupDetail>> => {
    const { data } = await apiClient.post('/buying-groups/create_group/', groupData);
    return { data };
  },

  /** @deprecated Use nearMe */
  nearby: async (params: { 
    postcode: string; 
    radius_km?: number 
  }): Promise<ApiResponse<PaginatedResponse<BuyingGroup>>> => {
    const { data } = await apiClient.get<PaginatedResponse<BuyingGroup>>('/buying-groups/near_me/', { 
      params: { postcode: params.postcode, radius: params.radius_km } 
    });
    return { data };
  },

  /** @deprecated Use commit */
  join: async (id: number, commitmentData: { 
    quantity: number; 
    buyer_postcode: string 
  }): Promise<ApiResponse<GroupCommitment>> => {
    const { data } = await apiClient.post<GroupCommitment>(`/buying-groups/${id}/commit/`, {
      quantity: commitmentData.quantity,
      postcode: commitmentData.buyer_postcode
    });
    return { data };
  },

  /** @deprecated Use cancelCommitment */
  leave: async (id: number): Promise<ApiResponse<{ message: string }>> => {
    const { data } = await apiClient.post<{ message: string }>(`/buying-groups/${id}/cancel_commitment/`);
    return { data };
  },

  /** @deprecated Use realtimeStatus */
  progress: async (id: number): Promise<ApiResponse<any>> => {
    const { data } = await apiClient.get(`/buying-groups/${id}/realtime_status/`);
    return { data };
  },
};

// Vendors endpoints
export const vendorsApi = {
  list: async (params?: { 
    page?: number;
    search?: string;
  }): Promise<ApiResponse<PaginatedResponse<Vendor>>> => {
    const { data } = await apiClient.get<PaginatedResponse<Vendor>>('/vendors/', { params });
    return { data };
  },

  get: async (id: number): Promise<ApiResponse<Vendor>> => {
    const { data } = await apiClient.get<Vendor>(`/vendors/${id}/`);
    return { data };
  },

  register: async (vendorData: VendorRegistrationData): Promise<ApiResponse<VendorRegistrationResponse>> => {
    const { data } = await apiClient.post<VendorRegistrationResponse>('/vendors/register/', vendorData);
    return { data };
  },

  searchByLocation: async (params: { 
    postcode: string; 
    radius_km?: number;
    min_rating?: number;
  }): Promise<ApiResponse<any>> => {
    const { data } = await apiClient.get('/vendors/search_by_location/', { params });
    return { data };
  },

  dashboard: async (id: number): Promise<ApiResponse<any>> => {
    const { data } = await apiClient.get(`/vendors/${id}/dashboard/`);
    return { data };
  },
};

// Orders endpoints
export const ordersApi = {
  list: async (params?: { 
    page?: number;
    status?: string;
    vendor?: number;
  }): Promise<ApiResponse<PaginatedResponse<Order>>> => {
    const { data } = await apiClient.get<PaginatedResponse<Order>>('/orders/', { params });
    return { data };
  },

  get: async (id: number): Promise<ApiResponse<OrderDetail>> => {
    const { data } = await apiClient.get<OrderDetail>(`/orders/${id}/`);
    return { data };
  },

  create: async (orderData: any): Promise<ApiResponse<OrderDetail>> => {
    const { data } = await apiClient.post<OrderDetail>('/orders/', orderData);
    return { data };
  },

  updateStatus: async (id: number, status: string, notes?: string): Promise<ApiResponse<any>> => {
    const { data } = await apiClient.post(`/orders/${id}/update_status/`, { status, notes });
    return { data };
  },

  cancel: async (id: number, reason?: string): Promise<ApiResponse<{ message: string }>> => {
    const { data } = await apiClient.post<{ message: string }>(`/orders/${id}/cancel/`, { reason });
    return { data };
  },

  processPayment: async (id: number, paymentMethodId: string): Promise<ApiResponse<any>> => {
    const { data } = await apiClient.post(`/orders/${id}/process_payment/`, { 
      payment_method_id: paymentMethodId 
    });
    return { data };
  },

  analytics: async (params?: { 
    date_from?: string; 
    date_to?: string;
    vendor_id?: number;
  }): Promise<ApiResponse<any>> => {
    const { data } = await apiClient.get('/orders/analytics/', { params });
    return { data };
  },
};

// Addresses endpoints - FIXED: Changed to PaginatedResponse
export const addressesApi = {
  list: async (): Promise<ApiResponse<PaginatedResponse<Address>>> => {
    const { data } = await apiClient.get<PaginatedResponse<Address>>('/addresses/');
    return { data };
  },

  get: async (id: number): Promise<ApiResponse<Address>> => {
    const { data } = await apiClient.get<Address>(`/addresses/${id}/`);
    return { data };
  },

  create: async (addressData: Omit<Address, 'id' | 'created_at'>): Promise<ApiResponse<Address>> => {
    const { data } = await apiClient.post<Address>('/addresses/', addressData);
    return { data };
  },

  update: async (id: number, addressData: Partial<Address>): Promise<ApiResponse<Address>> => {
    const { data } = await apiClient.patch<Address>(`/addresses/${id}/`, addressData);
    return { data };
  },

  delete: async (id: number): Promise<ApiResponse<void>> => {
    await apiClient.delete(`/addresses/${id}/`);
    return { data: undefined as void };
  },

  setDefault: async (id: number): Promise<ApiResponse<{ message: string; address: Address }>> => {
    const { data } = await apiClient.post<{ message: string; address: Address }>(`/addresses/${id}/set_default/`);
    return { data };
  },

  getDefault: async (): Promise<ApiResponse<Address>> => {
    const { data } = await apiClient.get<Address>('/addresses/default/');
    return { data };
  },
};

// Categories endpoint (for filters) - FIXED: Changed to PaginatedResponse
export const categoriesApi = {
  list: async (params?: { parent?: number | 'null' }): Promise<ApiResponse<PaginatedResponse<any>>> => {
    const { data } = await apiClient.get<PaginatedResponse<any>>('/categories/', { params });
    return { data };
  },

  get: async (id: number): Promise<ApiResponse<any>> => {
    const { data } = await apiClient.get(`/categories/${id}/`);
    return { data };
  },
};

// Tags endpoint (for filters)
export const tagsApi = {
  list: async (params?: { tag_type?: string }): Promise<ApiResponse<any[]>> => {
    const { data } = await apiClient.get('/tags/', { params });
    return { data };
  },

  get: async (id: number): Promise<ApiResponse<any>> => {
    const { data } = await apiClient.get(`/tags/${id}/`);
    return { data };
  },
};

// Cart endpoints
export const cartApi = {
  getCart: async (): Promise<ApiResponse<Cart>> => {
    const { data } = await apiClient.get<Cart>('/cart/');
    return { data };
  },

  addItem: async (productId: number, quantity: number = 1): Promise<ApiResponse<{
    message: string;
    item: CartItem;
    cart_items_count: number;
  }>> => {
    const { data } = await apiClient.post('/cart/add_item/', {
      product_id: productId,
      quantity,
    });
    return { data };
  },

  updateItem: async (itemId: number, quantity: number): Promise<ApiResponse<{
    message: string;
    item: CartItem;
  }>> => {
    const { data } = await apiClient.patch('/cart/update_item/', {
      item_id: itemId,
      quantity,
    });
    return { data };
  },

  removeItem: async (itemId: number): Promise<ApiResponse<{
    message: string;
    cart_items_count: number;
  }>> => {
    const { data } = await apiClient.delete(`/cart/remove_item/?item_id=${itemId}`);
    return { data };
  },

  clearCart: async (): Promise<ApiResponse<{ message: string }>> => {
    const { data } = await apiClient.delete('/cart/clear/');
    return { data };
  },

  getSummary: async (): Promise<ApiResponse<CartSummaryResponse>> => {
    const { data } = await apiClient.get<CartSummaryResponse>('/cart/summary/');
    return { data };
  },

  checkout: async (checkoutData: CheckoutRequest): Promise<ApiResponse<CheckoutResponse>> => {
    const { data } = await apiClient.post<CheckoutResponse>('/cart/checkout/', checkoutData);
    return { data };
  },
};

// Payments endpoints - FIXED: Added correct /api/v1/ prefix
export const paymentsApi = {
  createIntent: async (data: {
    amount: number;
    order_id?: number;
    group_id?: number;
    metadata?: Record<string, any>;
  }): Promise<ApiResponse<{
    client_secret: string;
    intent_id: string;
    amount: number;
    currency: string;
  }>> => {
    const { data: response } = await apiClient.post('/payments/create-intent/', data);
    return { data: response };
  },

  confirmPayment: async (data: {
    intent_id: string;
    payment_method_id: string;
  }): Promise<ApiResponse<{
    status: string;
    message: string;
    payment_intent: any;
  }>> => {
    const { data: response } = await apiClient.post('/payments/confirm-payment/', data);
    return { data: response };
  },

  getPaymentStatus: async (intentId: string): Promise<ApiResponse<{
    status: string;
    amount: number;
    currency: string;
    payment_method?: any;
    created_at: string;
  }>> => {
    const { data } = await apiClient.get(`/payments/payment-status/${intentId}/`);
    return { data };
  },

  createSetupIntent: async (data?: {
    customer_id?: string;
  }): Promise<ApiResponse<{
    client_secret: string;
    setup_intent_id: string;
  }>> => {
    const { data: response } = await apiClient.post('/payments/create-setup-intent/', data || {});
    return { data: response };
  },

  attachPaymentMethod: async (data: {
    payment_method_id: string;
    customer_id: string;
  }): Promise<ApiResponse<{
    message: string;
    payment_method: any;
  }>> => {
    const { data: response } = await apiClient.post('/payments/attach-payment-method/', data);
    return { data: response };
  },

  listPaymentMethods: async (customerId?: string): Promise<ApiResponse<{
    payment_methods: any[];
  }>> => {
    const { data } = await apiClient.get('/payments/payment-methods/', {
      params: customerId ? { customer_id: customerId } : undefined,
    });
    return { data };
  },

  createRefund: async (data: {
    payment_intent_id: string;
    amount?: number;
    reason?: string;
  }): Promise<ApiResponse<{
    refund_id: string;
    status: string;
    amount: number;
  }>> => {
    const { data: response } = await apiClient.post('/payments/create-refund/', data);
    return { data: response };
  },
};

// Additional types needed for WebSocket
export interface BuyingGroupRealtimeStatus {
  id: number;
  product_name: string;
  vendor_name: string;
  current_quantity: number;
  target_quantity: number;
  min_quantity: number;
  progress_percent: number;
  participants_count: number;
  time_remaining_seconds: number;
  status: string;
  discount_percent: string;
  savings_per_unit: string;
  area_name: string;
  expires_at: string;
}

export interface GroupUpdate {
  type: string;
  data: any;
  created_at: string;
}