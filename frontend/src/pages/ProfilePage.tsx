import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { EditProfileModal } from '@/components/profile/EditProfileModal';
import { ChangePasswordModal } from '@/components/profile/ChangePasswordModal';
import { DeleteAccountModal } from '@/components/profile/DeleteAccountModal';
import { AddressList } from '@/components/profile/AddressList';
import {
  User,
  Mail,
  Phone,
  Calendar,
  Store,
  Settings,
  Key,
  ShoppingBag,
  LogOut,
  Shield,
  Edit,
  MapPin,
  Plus,
} from 'lucide-react';

export function ProfilePage() {
  const { user, isVendor, logout } = useAuth();
  const navigate = useNavigate();
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [passwordModalOpen, setPasswordModalOpen] = useState(false);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);

  if (!user) {
    return (
      <div className="container mx-auto py-8">
        <Alert variant="destructive">
          <AlertDescription>Please log in to view your profile</AlertDescription>
        </Alert>
      </div>
    );
  }

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  const joinDate = new Date(user.date_joined).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });

  return (
    <div className="container mx-auto py-8 max-w-5xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">My Profile</h1>
          <p className="text-muted-foreground">Manage your account settings</p>
        </div>
        <Button variant="outline" onClick={handleLogout}>
          <LogOut className="h-4 w-4 mr-2" />
          Logout
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <User className="h-5 w-5" />
                Personal Information
              </CardTitle>
              <Button variant="outline" size="sm" onClick={() => setEditModalOpen(true)}>
                <Edit className="h-4 w-4 mr-2" />
                Edit
              </Button>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-sm text-muted-foreground">First Name</label>
                  <p className="font-medium">{user.first_name || 'Not set'}</p>
                </div>
                <div>
                  <label className="text-sm text-muted-foreground">Last Name</label>
                  <p className="font-medium">{user.last_name || 'Not set'}</p>
                </div>
              </div>

              <Separator />

              <div className="space-y-3">
                <div className="flex items-center gap-3">
                  <Mail className="h-4 w-4 text-muted-foreground" />
                  <div>
                    <label className="text-sm text-muted-foreground">Email</label>
                    <p className="font-medium">{user.email}</p>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <User className="h-4 w-4 text-muted-foreground" />
                  <div>
                    <label className="text-sm text-muted-foreground">Username</label>
                    <p className="font-medium">@{user.username}</p>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <Phone className="h-4 w-4 text-muted-foreground" />
                  <div>
                    <label className="text-sm text-muted-foreground">Phone Number</label>
                    <p className="font-medium">{user.phone_number || 'Not provided'}</p>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <Calendar className="h-4 w-4 text-muted-foreground" />
                  <div>
                    <label className="text-sm text-muted-foreground">Member Since</label>
                    <p className="font-medium">{joinDate}</p>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Shield className="h-5 w-5" />
                Security
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium">Password</p>
                </div>
                <Button variant="outline" onClick={() => setPasswordModalOpen(true)}>
                  <Key className="h-4 w-4 mr-2" />
                  Change Password
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <MapPin className="h-5 w-5" />
                Delivery Addresses
              </CardTitle>
              <Button variant="outline" size="sm" onClick={() => navigate('/addresses')}>
                <Plus className="h-4 w-4 mr-2" />
                Add Address
              </Button>
            </CardHeader>
            <CardContent>
              <AddressList />
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Account Type</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-sm">Buyer Account</span>
                <Badge variant="default">Active</Badge>
              </div>

              {isVendor && (
                <>
                  <Separator />
                  <div className="flex items-center justify-between">
                    <span className="text-sm">Vendor Account</span>
                    <Badge className="bg-green-100 text-green-800">Active</Badge>
                  </div>
                </>
              )}

              {user.is_staff && (
                <>
                  <Separator />
                  <div className="flex items-center justify-between">
                    <span className="text-sm">Staff Account</span>
                    <Badge variant="destructive">Admin</Badge>
                  </div>
                </>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Settings className="h-5 w-5" />
                Quick Actions
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <Button
                variant="outline"
                className="w-full justify-start"
                onClick={() => navigate('/orders')}
              >
                <ShoppingBag className="h-4 w-4 mr-2" />
                View My Orders
              </Button>

              {isVendor && (
                <Button
                  variant="outline"
                  className="w-full justify-start"
                  onClick={() => navigate('/vendors/dashboard')}
                >
                  <Store className="h-4 w-4 mr-2" />
                  Vendor Dashboard
                </Button>
              )}

              <Button
                variant="outline"
                className="w-full justify-start"
                onClick={() => navigate('/buying-groups')}
              >
                <User className="h-4 w-4 mr-2" />
                Browse Buying Groups
              </Button>
            </CardContent>
          </Card>

          <Card className="border-red-200">
            <CardHeader>
              <CardTitle className="text-lg text-red-600">Danger Zone</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Once you delete your account, there is no going back. Please be certain.
              </p>
              <Button 
                variant="destructive" 
                className="w-full"
                onClick={() => setDeleteModalOpen(true)}
              >
                Delete Account
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>

      <EditProfileModal
        open={editModalOpen}
        onOpenChange={setEditModalOpen}
        user={user}
      />
      <ChangePasswordModal
        open={passwordModalOpen}
        onOpenChange={setPasswordModalOpen}
      />
      <DeleteAccountModal
        open={deleteModalOpen}
        onOpenChange={setDeleteModalOpen}
      />
    </div>
  );
}