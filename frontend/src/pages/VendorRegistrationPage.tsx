// frontend/src/pages/VendorRegistrationPage.tsx
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { useMutation } from '@tanstack/react-query';
import { vendorsApi, VendorRegistrationData as ApiVendorRegistrationData } from '@/api/endpoints';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Separator } from '@/components/ui/separator';
import { Badge } from '@/components/ui/badge';
import {
  Store,
  MapPin,
  FileText,
  CheckCircle,
  AlertCircle,
  Info,
  Loader2,
} from 'lucide-react';

// Validation schema matching backend requirements
const vendorRegistrationSchema = z.object({
  business_name: z.string()
    .min(2, 'Business name must be at least 2 characters')
    .max(200, 'Business name must be less than 200 characters'),
  
  description: z.string()
    .min(10, 'Description must be at least 10 characters')
    .max(1000, 'Description must be less than 1000 characters'),
  
  postcode: z.string()
    .regex(
      /^[A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2}$/i,
      'Invalid UK postcode format (e.g., SW1A 1AA)'
    )
    .transform(val => val.toUpperCase().replace(/\s+/g, ' ')),
  
  phone_number: z.string()
    .regex(
      /^(?:(?:\+44)|(?:0))(?:\d\s?){10,11}$/,
      'Invalid UK phone number (e.g., +44 7700 900000 or 07700 900000)'
    )
    .optional()
    .or(z.literal('')),
  
  delivery_radius_km: z.preprocess(
    (val) => Number(val),
    z.number()
      .min(1, 'Delivery radius must be at least 1 km')
      .max(100, 'Delivery radius cannot exceed 100 km')
  ),
  
  min_order_value: z.preprocess(
    (val) => Number(val),
    z.number()
      .min(0, 'Minimum order value cannot be negative')
      .max(10000, 'Minimum order value seems too high')
  ),
  
  vat_number: z.string()
    .regex(/^GB\d{9}$/, 'Invalid VAT number format (e.g., GB123456789)')
    .optional()
    .or(z.literal('')),
  
  logo_url: z.string()
    .url('Invalid URL format')
    .optional()
    .or(z.literal('')),
});

export default function VendorRegistrationPage() {
  const navigate = useNavigate();
  const { user, refreshUser } = useAuth();
  const [success, setSuccess] = useState(false);
  const [fsaVerified, setFsaVerified] = useState<boolean | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(vendorRegistrationSchema),
    defaultValues: {
      delivery_radius_km: '10',
      min_order_value: '50',
    },
  });

  const registerMutation = useMutation({
    mutationFn: (data: ApiVendorRegistrationData) => vendorsApi.register(data),
    onSuccess: async (response) => {
      setSuccess(true);
      setFsaVerified(response.data.fsa_verified);
      // Refresh user data to update vendor status
      await refreshUser();
      
      // Show success for 3 seconds, then redirect
      setTimeout(() => {
        navigate('/vendors/dashboard');
      }, 3000);
    },
  });

  if (!user) {
    return (
      <div className="container mx-auto px-4 py-8 max-w-2xl">
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            Please <a href="/login" className="underline">log in</a> to register as a vendor.
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  if (success) {
    return (
      <div className="container mx-auto px-4 py-8 max-w-2xl">
        <Card className="border-green-200 bg-green-50">
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="p-3 bg-green-100 rounded-full">
                <CheckCircle className="h-6 w-6 text-green-600" />
              </div>
              <div>
                <CardTitle className="text-green-900">Registration Successful!</CardTitle>
                <CardDescription className="text-green-700">
                  Your vendor account has been created
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              {fsaVerified ? (
                <div className="flex items-start gap-2">
                  <CheckCircle className="h-5 w-5 text-green-600 mt-0.5" />
                  <div>
                    <p className="font-medium text-green-900">FSA Verified</p>
                    <p className="text-sm text-green-700">
                      Your Food Standards Agency rating has been confirmed
                    </p>
                  </div>
                </div>
              ) : (
                <div className="flex items-start gap-2">
                  <Info className="h-5 w-5 text-yellow-600 mt-0.5" />
                  <div>
                    <p className="font-medium text-yellow-900">FSA Verification Pending</p>
                    <p className="text-sm text-yellow-700">
                      We'll verify your FSA rating during admin review
                    </p>
                  </div>
                </div>
              )}
              
              <div className="flex items-start gap-2">
                <CheckCircle className="h-5 w-5 text-green-600 mt-0.5" />
                <div>
                  <p className="font-medium text-green-900">Stripe Account Created</p>
                  <p className="text-sm text-green-700">
                    Complete Stripe onboarding in your dashboard
                  </p>
                </div>
              </div>
              
              <div className="flex items-start gap-2">
                <Info className="h-5 w-5 text-yellow-600 mt-0.5" />
                <div>
                  <p className="font-medium text-green-900">Pending Admin Approval</p>
                  <p className="text-sm text-green-700">
                    Your account will be reviewed within 24-48 hours
                  </p>
                </div>
              </div>
            </div>

            <p className="text-sm text-green-700">
              Redirecting to your vendor dashboard...
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8 max-w-4xl">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <Store className="h-8 w-8 text-primary" />
          <h1 className="text-3xl font-bold">Become a Vendor</h1>
        </div>
        <p className="text-muted-foreground">
          Join our marketplace and start selling to restaurants and cafes across the UK
        </p>
      </div>

      {/* Info Alert */}
      <Alert className="mb-6">
        <Info className="h-4 w-4" />
        <AlertDescription>
          <strong>What happens next:</strong> After registration, your FSA rating will be verified,
          you'll complete Stripe onboarding, and our team will review your application within 24-48 hours.
        </AlertDescription>
      </Alert>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Registration Form */}
        <div className="lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>Vendor Registration</CardTitle>
              <CardDescription>
                Provide your business details to get started
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form 
                onSubmit={handleSubmit((data) => 
                  registerMutation.mutate(data as unknown as ApiVendorRegistrationData)
                )} 
                className="space-y-6"
              >
                {/* Error Alert */}
                {registerMutation.isError && (
                  <Alert variant="destructive">
                    <AlertCircle className="h-4 w-4" />
                    <AlertDescription>
                      {(registerMutation.error as any)?.response?.data?.error || 
                       (registerMutation.error as any)?.response?.data?.business_name?.[0] ||
                       'Registration failed. Please try again.'}
                    </AlertDescription>
                  </Alert>
                )}

                {/* Business Information */}
                <div className="space-y-4">
                  <h3 className="text-lg font-semibold flex items-center gap-2">
                    <Store className="h-5 w-5" />
                    Business Information
                  </h3>

                  <div className="space-y-2">
                    <Label htmlFor="business_name">
                      Business Name <span className="text-red-500">*</span>
                    </Label>
                    <Input
                      id="business_name"
                      {...register('business_name')}
                      placeholder="e.g., Borough Market Organics"
                    />
                    {errors.business_name && (
                      <p className="text-sm text-destructive">{errors.business_name.message}</p>
                    )}
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="description">
                      Description <span className="text-red-500">*</span>
                    </Label>
                    <Textarea
                      id="description"
                      {...register('description')}
                      placeholder="Describe your business, products, and what makes you unique..."
                      rows={4}
                    />
                    {errors.description && (
                      <p className="text-sm text-destructive">{errors.description.message}</p>
                    )}
                    <p className="text-xs text-muted-foreground">
                      This will be shown on your public vendor profile
                    </p>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="vat_number">
                      VAT Number <span className="text-muted-foreground">(Optional)</span>
                    </Label>
                    <Input
                      id="vat_number"
                      {...register('vat_number')}
                      placeholder="GB123456789"
                    />
                    {errors.vat_number && (
                      <p className="text-sm text-destructive">{errors.vat_number.message}</p>
                    )}
                  </div>
                </div>

                <Separator />

                {/* Contact & Location */}
                <div className="space-y-4">
                  <h3 className="text-lg font-semibold flex items-center gap-2">
                    <MapPin className="h-5 w-5" />
                    Contact & Location
                  </h3>

                  <div className="space-y-2">
                    <Label htmlFor="postcode">
                      Business Postcode <span className="text-red-500">*</span>
                    </Label>
                    <Input
                      id="postcode"
                      {...register('postcode')}
                      placeholder="SW1A 1AA"
                      className="uppercase"
                    />
                    {errors.postcode && (
                      <p className="text-sm text-destructive">{errors.postcode.message}</p>
                    )}
                    <p className="text-xs text-muted-foreground">
                      Used for FSA verification and location-based services
                    </p>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="phone_number">
                      Phone Number <span className="text-muted-foreground">(Optional)</span>
                    </Label>
                    <Input
                      id="phone_number"
                      {...register('phone_number')}
                      placeholder="+44 7700 900000 or 07700 900000"
                    />
                    {errors.phone_number && (
                      <p className="text-sm text-destructive">{errors.phone_number.message}</p>
                    )}
                  </div>
                </div>

                <Separator />

                {/* Delivery Settings */}
                <div className="space-y-4">
                  <h3 className="text-lg font-semibold flex items-center gap-2">
                    <FileText className="h-5 w-5" />
                    Delivery Settings
                  </h3>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label htmlFor="delivery_radius_km">
                        Delivery Radius (km) <span className="text-red-500">*</span>
                      </Label>
                      <Input
                        id="delivery_radius_km"
                        type="number"
                        {...register('delivery_radius_km')}
                        min="1"
                        max="100"
                        defaultValue="10"
                      />
                      {errors.delivery_radius_km && (
                        <p className="text-sm text-destructive">{errors.delivery_radius_km.message}</p>
                      )}
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="min_order_value">
                        Minimum Order (£) <span className="text-red-500">*</span>
                      </Label>
                      <Input
                        id="min_order_value"
                        type="number"
                        {...register('min_order_value')}
                        min="0"
                        step="0.01"
                        defaultValue="50"
                      />
                      {errors.min_order_value && (
                        <p className="text-sm text-destructive">{errors.min_order_value.message}</p>
                      )}
                    </div>
                  </div>
                </div>

                <Separator />

                {/* Optional: Logo */}
                <div className="space-y-4">
                  <h3 className="text-lg font-semibold">Branding (Optional)</h3>

                  <div className="space-y-2">
                    <Label htmlFor="logo_url">
                      Logo URL <span className="text-muted-foreground">(Optional)</span>
                    </Label>
                    <Input
                      id="logo_url"
                      {...register('logo_url')}
                      placeholder="https://example.com/logo.png"
                    />
                    {errors.logo_url && (
                      <p className="text-sm text-destructive">{errors.logo_url.message}</p>
                    )}
                    <p className="text-xs text-muted-foreground">
                      Provide a URL to your business logo (you can update this later)
                    </p>
                  </div>
                </div>

                {/* Submit Button */}
                <Button 
                  type="submit" 
                  className="w-full" 
                  size="lg"
                  disabled={registerMutation.isPending}
                >
                  {registerMutation.isPending ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Registering...
                    </>
                  ) : (
                    <>
                      <Store className="h-4 w-4 mr-2" />
                      Register as Vendor
                    </>
                  )}
                </Button>
              </form>
            </CardContent>
          </Card>
        </div>

        {/* Sidebar - Benefits */}
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Why Become a Vendor?</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-start gap-2">
                <CheckCircle className="h-5 w-5 text-green-600 mt-0.5" />
                <div>
                  <p className="font-medium text-sm">Reach More Buyers</p>
                  <p className="text-xs text-muted-foreground">
                    Connect with restaurants and cafes across the UK
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-2">
                <CheckCircle className="h-5 w-5 text-green-600 mt-0.5" />
                <div>
                  <p className="font-medium text-sm">Automated Payments</p>
                  <p className="text-xs text-muted-foreground">
                    Secure payouts via Stripe Connect
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-2">
                <CheckCircle className="h-5 w-5 text-green-600 mt-0.5" />
                <div>
                  <p className="font-medium text-sm">FSA Verified</p>
                  <p className="text-xs text-muted-foreground">
                    Build trust with verified ratings
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-2">
                <CheckCircle className="h-5 w-5 text-green-600 mt-0.5" />
                <div>
                  <p className="font-medium text-sm">Group Buying</p>
                  <p className="text-xs text-muted-foreground">
                    Increase sales with location-based group orders
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Registration Process</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex gap-3">
                <Badge variant="outline" className="h-6 w-6 rounded-full p-0 flex items-center justify-center">
                  1
                </Badge>
                <div>
                  <p className="font-medium text-sm">Submit Details</p>
                  <p className="text-xs text-muted-foreground">
                    Provide business information
                  </p>
                </div>
              </div>

              <div className="flex gap-3">
                <Badge variant="outline" className="h-6 w-6 rounded-full p-0 flex items-center justify-center">
                  2
                </Badge>
                <div>
                  <p className="font-medium text-sm">FSA Verification</p>
                  <p className="text-xs text-muted-foreground">
                    Automatic rating check
                  </p>
                </div>
              </div>

              <div className="flex gap-3">
                <Badge variant="outline" className="h-6 w-6 rounded-full p-0 flex items-center justify-center">
                  3
                </Badge>
                <div>
                  <p className="font-medium text-sm">Stripe Onboarding</p>
                  <p className="text-xs text-muted-foreground">
                    Set up payment account
                  </p>
                </div>
              </div>

              <div className="flex gap-3">
                <Badge variant="outline" className="h-6 w-6 rounded-full p-0 flex items-center justify-center">
                  4
                </Badge>
                <div>
                  <p className="font-medium text-sm">Admin Review</p>
                  <p className="text-xs text-muted-foreground">
                    24-48 hour approval
                  </p>
                </div>
              </div>

              <div className="flex gap-3">
                <Badge variant="outline" className="h-6 w-6 rounded-full p-0 flex items-center justify-center">
                  5
                </Badge>
                <div>
                  <p className="font-medium text-sm">Start Selling</p>
                  <p className="text-xs text-muted-foreground">
                    List products and accept orders
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}