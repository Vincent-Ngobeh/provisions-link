// API Response types
export interface ApiResponse<T> {
  data: T;
  message?: string;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// User types
export interface User {
  id: number;
  email: string;
  username: string;
  first_name: string;
  last_name: string;
  phone_number: string;
  date_joined: string;
  has_vendor_account: boolean;
}

// Auth types
export interface LoginCredentials {
  email_or_username: string;
  password: string;
}

export interface RegisterData {
  email: string;
  username: string;
  password: string;
  password_confirm: string;
  first_name: string;
  last_name: string;
  phone_number?: string;
}

export interface AuthTokens {
  access: string;
  refresh: string;
}

export interface AuthResponse {
  user: User;
  tokens: AuthTokens;
  is_vendor: boolean;
  vendor?: Vendor;
}

// Vendor types
export interface Vendor {
  id: number;
  business_name: string;
  slug: string;
  description: string;
  fsa_rating_value: number | null;
  fsa_rating_display: string;
  delivery_radius_km: number;
  min_order_value: string;
  logo_url: string;
  distance_km?: string;
}

// Product types
export interface Product {
  id: number;
  name: string;
  slug: string;
  vendor: Vendor;
  category_name: string;
  price: string;
  price_with_vat: string;
  unit: string;
  primary_image: string;
  in_stock: boolean;
  contains_allergens: boolean;
  active_group?: ActiveGroup;
}

export interface ProductDetail extends Product {
  description: string;
  sku: string;
  barcode: string;
  stock_quantity: number;
  allergen_info: Record<string, boolean>;
  allergen_statement: string;
  additional_images: string[];
}

// Buying Group types
export interface BuyingGroup {
  id: number;
  product_name: string;
  vendor_name: string;
  area_name: string;
  target_quantity: number;
  current_quantity: number;
  discount_percent: string;
  progress_percent: number;
  time_remaining: string;
  expires_at: string;
  status: 'open' | 'active' | 'failed' | 'completed';
}

export interface BuyingGroupDetail extends BuyingGroup {
  product: Product;
  center_point: {
    type: string;
    coordinates: [number, number];
  };
  radius_km: number;
  min_quantity: number;
  savings_per_unit: string;
  discounted_price: string;
  participants_count: number;
  created_at: string;
}

export interface ActiveGroup {
  id: number;
  discount_percent: string;
  current_quantity: number;
  target_quantity: number;
  expires_at: string;
}

// WebSocket types
export interface WebSocketMessage {
  type: string;
  data: any;
}

export interface GroupProgressUpdate {
  group_id: number;
  current_quantity: number;
  target_quantity: number;
  progress_percent: number;
  participants_count: number;
  time_remaining_seconds?: number;
}

// Order types
export interface Order {
  id: number;
  reference_number: string;
  vendor_name: string;
  total: string;
  status: string;
  items_count: number;
  created_at: string;
}

// Address types
export interface Address {
  id: number;
  address_name: string;
  recipient_name: string;
  phone_number: string;
  line1: string;
  line2: string;
  city: string;
  postcode: string;
  country: string;
  is_default: boolean;
  created_at: string;
}