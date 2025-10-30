// frontend/src/components/profile/EditProfileModal.tsx
// FIXED: Properly handles response structure from backend

import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useAuth } from '@/contexts/AuthContext';
import { authApi } from '@/api/endpoints';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { useToast } from '@/hooks/use-toast';
import { Loader2 } from 'lucide-react';
import type { User } from '@/types';

interface EditProfileModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  user: User;
}

export function EditProfileModal({ open, onOpenChange, user }: EditProfileModalProps) {
  const { refreshUser } = useAuth();
  const { toast } = useToast();
  const [error, setError] = useState('');

  const [formData, setFormData] = useState({
    first_name: user.first_name,
    last_name: user.last_name,
    phone_number: user.phone_number,
  });

  const updateMutation = useMutation({
    mutationFn: async (data: typeof formData) => {
      return authApi.updateProfile(data);
    },
    onSuccess: async (response) => {
      // Backend returns: { data: { message: string, user: User } }
      // response.data.message is now properly typed
      await refreshUser();
      
      toast({
        title: 'Profile Updated',
        description: response.data.message || 'Your profile has been successfully updated.',
      });
      
      onOpenChange(false);
      setError('');
    },
    onError: (error: any) => {
      // Handle various error response formats from backend
      let message = 'Failed to update profile';
      
      if (error.response?.data) {
        const data = error.response.data;
        
        // Check for different error formats
        if (typeof data === 'string') {
          message = data;
        } else if (data.error) {
          message = data.error;
        } else if (data.message) {
          message = data.message;
        } else if (data.detail) {
          message = data.detail;
        } else if (typeof data === 'object') {
          // Handle field validation errors (e.g., {first_name: ['This field is required']})
          const errors = Object.values(data);
          if (errors.length > 0) {
            const firstError = errors[0];
            if (Array.isArray(firstError) && firstError.length > 0) {
              message = firstError[0];
            } else if (typeof firstError === 'string') {
              message = firstError;
            }
          }
        }
      }
      
      setError(message);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    // Basic validation
    if (!formData.first_name.trim() || !formData.last_name.trim()) {
      setError('First name and last name are required');
      return;
    }

    // Validate phone number if provided (UK format)
    if (formData.phone_number && formData.phone_number.trim()) {
      // Remove spaces for validation
      const cleanPhone = formData.phone_number.replace(/\s/g, '');
      // UK phone regex: starts with +44 or 0, followed by 10-11 digits
      const phoneRegex = /^(?:(?:\+44)|(?:0))(?:\d){10,11}$/;
      
      if (!phoneRegex.test(cleanPhone)) {
        setError('Please enter a valid UK phone number (e.g., +447700900000 or 07700900000)');
        return;
      }
    }

    updateMutation.mutate(formData);
  };

  const handleChange = (field: keyof typeof formData) => (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    setFormData(prev => ({ ...prev, [field]: e.target.value }));
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Edit Profile</DialogTitle>
          <DialogDescription>
            Update your personal information
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="first_name">First Name *</Label>
            <Input
              id="first_name"
              value={formData.first_name}
              onChange={handleChange('first_name')}
              placeholder="Enter your first name"
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="last_name">Last Name *</Label>
            <Input
              id="last_name"
              value={formData.last_name}
              onChange={handleChange('last_name')}
              placeholder="Enter your last name"
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="phone_number">Phone Number</Label>
            <Input
              id="phone_number"
              type="tel"
              value={formData.phone_number}
              onChange={handleChange('phone_number')}
              placeholder="+447700900000 or 07700900000"
            />
            <p className="text-xs text-muted-foreground">
              UK format: +44 or 0 followed by 10-11 digits
            </p>
          </div>

          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={updateMutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={updateMutation.isPending}>
              {updateMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Saving...
                </>
              ) : (
                'Save Changes'
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}