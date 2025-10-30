// frontend/src/components/profile/ChangePasswordModal.tsx
// CORRECTED: Field names now match backend (old_password, new_password_confirm)

import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
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
import { Loader2, Eye, EyeOff } from 'lucide-react';

interface ChangePasswordModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ChangePasswordModal({ open, onOpenChange }: ChangePasswordModalProps) {
  const { toast } = useToast();
  const [error, setError] = useState('');
  const [showPasswords, setShowPasswords] = useState({
    current: false,
    new: false,
    confirm: false,
  });

  // Backend expects: old_password, new_password, new_password_confirm
  const [formData, setFormData] = useState({
    old_password: '',
    new_password: '',
    new_password_confirm: '',
  });

  const changePasswordMutation = useMutation({
    mutationFn: async (data: typeof formData) => {
      return authApi.changePassword(data);
    },
    onSuccess: (response) => {
      // Backend returns new tokens after password change
      if (response.data.tokens) {
        localStorage.setItem('access_token', response.data.tokens.access);
        localStorage.setItem('refresh_token', response.data.tokens.refresh);
      }

      toast({
        title: 'Password Changed',
        description: response.data.message || 'Your password has been successfully updated.',
      });
      
      onOpenChange(false);
      setFormData({
        old_password: '',
        new_password: '',
        new_password_confirm: '',
      });
      setError('');
    },
    onError: (error: any) => {
      // Backend returns validation errors
      const message = error.response?.data?.error || 
                     error.response?.data?.message || 
                     'Failed to change password';
      setError(message);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    // Client-side validation
    if (!formData.old_password) {
      setError('Current password is required');
      return;
    }

    if (formData.new_password.length < 8) {
      setError('New password must be at least 8 characters');
      return;
    }

    if (formData.new_password !== formData.new_password_confirm) {
      setError('New passwords do not match');
      return;
    }

    if (formData.old_password === formData.new_password) {
      setError('New password must be different from current password');
      return;
    }

    // Send to backend - backend will do server-side validation too
    changePasswordMutation.mutate(formData);
  };

  const handleChange = (field: keyof typeof formData) => (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    setFormData(prev => ({ ...prev, [field]: e.target.value }));
  };

  const toggleShowPassword = (field: keyof typeof showPasswords) => {
    setShowPasswords(prev => ({ ...prev, [field]: !prev[field] }));
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Change Password</DialogTitle>
          <DialogDescription>
            Enter your current password and choose a new one
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Current Password */}
          <div className="space-y-2">
            <Label htmlFor="old_password">Current Password *</Label>
            <div className="relative">
              <Input
                id="old_password"
                type={showPasswords.current ? 'text' : 'password'}
                value={formData.old_password}
                onChange={handleChange('old_password')}
                placeholder="Enter current password"
                required
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="absolute right-0 top-0 h-full px-3"
                onClick={() => toggleShowPassword('current')}
              >
                {showPasswords.current ? (
                  <EyeOff className="h-4 w-4" />
                ) : (
                  <Eye className="h-4 w-4" />
                )}
              </Button>
            </div>
          </div>

          {/* New Password */}
          <div className="space-y-2">
            <Label htmlFor="new_password">New Password *</Label>
            <div className="relative">
              <Input
                id="new_password"
                type={showPasswords.new ? 'text' : 'password'}
                value={formData.new_password}
                onChange={handleChange('new_password')}
                placeholder="Enter new password"
                required
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="absolute right-0 top-0 h-full px-3"
                onClick={() => toggleShowPassword('new')}
              >
                {showPasswords.new ? (
                  <EyeOff className="h-4 w-4" />
                ) : (
                  <Eye className="h-4 w-4" />
                )}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Must be at least 8 characters long
            </p>
          </div>

          {/* Confirm Password */}
          <div className="space-y-2">
            <Label htmlFor="new_password_confirm">Confirm New Password *</Label>
            <div className="relative">
              <Input
                id="new_password_confirm"
                type={showPasswords.confirm ? 'text' : 'password'}
                value={formData.new_password_confirm}
                onChange={handleChange('new_password_confirm')}
                placeholder="Confirm new password"
                required
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="absolute right-0 top-0 h-full px-3"
                onClick={() => toggleShowPassword('confirm')}
              >
                {showPasswords.confirm ? (
                  <EyeOff className="h-4 w-4" />
                ) : (
                  <Eye className="h-4 w-4" />
                )}
              </Button>
            </div>
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
              disabled={changePasswordMutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={changePasswordMutation.isPending}>
              {changePasswordMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Changing...
                </>
              ) : (
                'Change Password'
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}