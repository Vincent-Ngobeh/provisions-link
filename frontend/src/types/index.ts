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
  is_staff?: boolean; // Django built-in field, may not always be sent
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
  logo_url?: string;
  distance_km?: string;
  phone_number?: string; 
  is_approved?: boolean; 
  fsa_verified?: boolean; 
  stripe_onboarding_complete?: boolean;
  postcode?: string; 
  created_at?: string; 
  fsa_rating_date?: string;
  products_count?: number;
  active_groups_count?: number;
}

export interface VendorDashboard {
  id: number;
  business_name: string;
  stripe_onboarding_complete: boolean;
  commission_rate: string;
  today_revenue: string;
  pending_orders: number;
  low_stock_products: number;
  fsa_rating_value: number | null;
  fsa_last_checked: string | null;
}

// Tag types
export interface Tag {
  id: number;
  name: string;
  slug: string;
  tag_type: 'dietary' | 'organic' | 'origin' | 'preparation' | 'other';
}

// Product types (unified - contains all fields)
export interface Product {
  id: number;
  name: string;
  slug: string;
  description: string;
  sku: string;
  barcode?: string;
  vendor: Vendor;
  category_name: string;
  category?: {           
    id: number;
    name: string;
    slug: string;
    parent: number | null;
    display_order: number;
  };
  price: string;
  price_with_vat: string;
  vat_rate: string;
  unit: string;
  stock_quantity: number;
  low_stock_threshold: number;
  primary_image?: string;
  additional_images: string[];
  in_stock: boolean;
  contains_allergens: boolean;
  allergen_info: Record<string, boolean>;
  allergen_statement?: string;
  tags?: Tag[];
  active_group?: ActiveGroup;
  created_at: string;
}

// Active Group types
export interface ActiveGroup {
  id: number;
  discount_percent: string;
  current_quantity: number;
  target_quantity: number;
  min_quantity: number;
  expires_at: string;
  progress_percent: number;
}

// Buying Group types
export interface BuyingGroup {
  id: number;
  product_name: string;
  vendor_name: string;
  area_name: string;
  target_quantity: number;
  current_quantity: number;
  min_quantity: number;
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
  group?: number | null;
}

export interface OrderDetail extends Order {
  buyer: {
    id: number;
    email: string;
    first_name: string;
    last_name: string;
  };
  vendor: Vendor;
  delivery_address: Address;
  items: OrderItem[];
  subtotal: string;
  vat_amount: string;
  delivery_fee: string;
  marketplace_fee?: string;
  vendor_payout?: string;
  delivery_notes?: string;
  paid_at?: string;
  delivered_at?: string;
  stripe_payment_intent_id?: string; // Exists in model but not always exposed
}

export interface OrderItem {
  id: number;
  product: Product;
  quantity: number;
  unit_price: string;
  total_price: string;
  discount_amount: string;
  vat_amount: string;
}

// Address types
export interface Address {
  id: number;
  address_name: string;
  recipient_name: string;
  phone_number: string;
  line1: string;
  line2?: string;
  city: string;
  postcode: string;
  country: string;
  is_default: boolean;
  created_at: string;
}

// Group Commitment types
export interface GroupCommitment {
  id: number;
  group: number;
  quantity: number;
  buyer_postcode: string;
  total_price: string;
  total_savings: string;
  status: 'pending' | 'confirmed' | 'cancelled';
  committed_at: string;
  order?: number | null;  // Order ID when confirmed
}

// Cart types
export interface CartItem {
  id: number;
  product: Product;
  product_id?: number;
  quantity: number;
  subtotal: string;
  vat_amount: string;
  total_with_vat: string;
  added_at: string;
  updated_at: string;
}

export interface Cart {
  id: number;
  items: CartItem[];
  items_count: number;
  total_value: string;
  subtotal: string;
  vat_total: string;
  grand_total: string;
  vendors_count: number;
  created_at: string;
  updated_at: string;
}

export interface VendorCartSummary {
  vendor_id: number;
  vendor_name: string;
  items_count: number;
  subtotal: string;
  vat: string;
  total: string;
  min_order_value: string;
  meets_minimum: boolean;
  items: CartItem[];
}

export interface CartSummaryResponse {
  vendors: VendorCartSummary[];
  total_vendors: number;
  grand_total: string;
}

export interface CheckoutRequest {
  delivery_address_id: number;
  delivery_notes?: string;
}

export interface CheckoutResponse {
  message: string;
  orders: {
    order_id: number;
    reference_number: string;
    vendor_name: string;
    total: string;
    items_count: number;
  }[];
  failed_vendors?: {
    vendor_name: string;
    error: string;
    error_code: string;
  }[] | null;
}