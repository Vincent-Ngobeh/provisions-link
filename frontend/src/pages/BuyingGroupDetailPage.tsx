// frontend/src/pages/BuyingGroupDetailPage.tsx
// Detail page with real-time WebSocket updates

import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { buyingGroupsApi } from '@/api/endpoints';
import { useGroupBuyingWebSocket } from '@/hooks/useGroupBuyingWebSocket';
import { useAuth } from '@/contexts/AuthContext';
import { GroupProgress } from '@/components/buying-groups/GroupProgress';
import { CountdownTimer } from '@/components/buying-groups/CountdownTimer';
import { ParticipantsList } from '@/components/buying-groups/ParticipantsList';
import { JoinGroupModal } from '@/components/buying-groups/JoinGroupModal';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';
import { useToast } from '@/hooks/use-toast';
import {
  ArrowLeft,
  Store,
  MapPin,
  Tag,
  Wifi,
  WifiOff,
  CheckCircle,
  AlertCircle,
  Info,
  TrendingUp,
  Users,
  Target,
} from 'lucide-react';

export default function BuyingGroupDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  
  const [showJoinModal, setShowJoinModal] = useState(false);
  const [realtimeData, setRealtimeData] = useState<any>(null);

  // Fetch group details
  const { data: groupData, isLoading } = useQuery({
    queryKey: ['buying-group', id],
    queryFn: () => buyingGroupsApi.get(parseInt(id!)),
    enabled: !!id,
  });

  const group = groupData?.data;

  // WebSocket connection with callbacks
  const {
    isConnected,
    lastUpdate,
  } = useGroupBuyingWebSocket({
    groupId: id ? parseInt(id) : null,
    autoConnect: true,
    onProgressUpdate: (data) => {
      setRealtimeData(data);
      
      // Show toast for threshold milestones
      if (data.progress_percent >= 80 && data.progress_percent < 85) {
        toast({
          title: '🎉 Almost there!',
          description: `This group is at ${data.progress_percent.toFixed(0)}% of target!`,
        });
      }
    },
    onThresholdReached: (data) => {
      toast({
        title: `🎯 ${data.threshold_percent}% Milestone Reached!`,
        description: data.message,
        duration: 5000,
      });
    },
    onStatusChange: (data) => {
      toast({
        title: 'Status Updated',
        description: data.message,
        variant: data.new_status === 'active' ? 'default' : 'destructive',
      });

      // Refresh group data
      queryClient.invalidateQueries({ queryKey: ['buying-group', id] });
    },
    onNewCommitment: (data) => {
      toast({
        title: '✨ New Participant!',
        description: data.message,
        duration: 3000,
      });
    },
    onCommitmentCancelled: (data) => {
      toast({
        title: 'Commitment Cancelled',
        description: data.message,
        duration: 3000,
      });
    },
  });

  // Use realtime data if available, otherwise use group data
  const currentQuantity = realtimeData?.current_quantity ?? group?.current_quantity ?? 0;
  const targetQuantity = realtimeData?.target_quantity ?? group?.target_quantity ?? 0;
  const progressPercent = realtimeData?.progress_percent ?? group?.progress_percent ?? 0;
  const participantsCount = realtimeData?.participants_count ?? group?.participants_count ?? 0;

  if (isLoading) {
    return (
      <div className="container mx-auto px-4 py-8 max-w-5xl">
        <Skeleton className="h-12 w-32 mb-6" />
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            <Skeleton className="h-96" />
            <Skeleton className="h-64" />
          </div>
          <Skeleton className="h-96" />
        </div>
      </div>
    );
  }

  if (!group) {
    return (
      <div className="container mx-auto px-4 py-8 text-center">
        <AlertCircle className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
        <h2 className="text-2xl font-bold mb-2">Group Not Found</h2>
        <p className="text-muted-foreground mb-4">
          This buying group doesn't exist or has been removed.
        </p>
        <Button onClick={() => navigate('/buying-groups')}>
          <ArrowLeft className="h-4 w-4 mr-2" />
          Back to Groups
        </Button>
      </div>
    );
  }

  const discountedPrice = parseFloat(group.discounted_price);
  const savingsPerUnit = parseFloat(group.savings_per_unit);

  return (
    <div className="container mx-auto px-4 py-8 max-w-5xl">
      {/* Back Button */}
      <Button
        variant="ghost"
        onClick={() => navigate('/buying-groups')}
        className="mb-6"
      >
        <ArrowLeft className="h-4 w-4 mr-2" />
        Back to Groups
      </Button>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Content */}
        <div className="lg:col-span-2 space-y-6">
          {/* Header Card */}
          <Card>
            <CardHeader>
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    <h1 className="text-2xl font-bold">{group.product.name}</h1>
                    <Badge
                      variant={group.status === 'open' ? 'default' : 'secondary'}
                    >
                      {group.status.toUpperCase()}
                    </Badge>
                  </div>

                  <div className="space-y-2">
                    <div className="flex items-center gap-2 text-muted-foreground">
                      <Store className="h-4 w-4" />
                      <span>{group.product.vendor.business_name}</span>
                    </div>

                    <div className="flex items-center gap-2 text-muted-foreground">
                      <MapPin className="h-4 w-4" />
                      <span>{group.area_name} (within {group.radius_km}km)</span>
                    </div>
                  </div>
                </div>

                {/* WebSocket Status Indicator */}
                <div className="flex items-center gap-2">
                  {isConnected ? (
                    <Badge variant="outline" className="border-green-500 text-green-700">
                      <Wifi className="h-3 w-3 mr-1" />
                      Live
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="border-gray-400">
                      <WifiOff className="h-3 w-3 mr-1" />
                      Offline
                    </Badge>
                  )}
                </div>
              </div>
            </CardHeader>

            <CardContent className="space-y-6">
              {/* Real-Time Progress */}
              <div>
                <h3 className="font-semibold mb-3 flex items-center gap-2">
                  <TrendingUp className="h-4 w-4" />
                  Progress
                  {lastUpdate && (
                    <span className="text-xs text-green-600 animate-pulse">
                      ● Updated
                    </span>
                  )}
                </h3>
                <GroupProgress
                  currentQuantity={currentQuantity}
                  targetQuantity={targetQuantity}
                  minQuantity={group.min_quantity}
                  progressPercent={progressPercent}
                  participantsCount={participantsCount}
                  animate={true}
                />
              </div>

              {/* Countdown and Participants */}
              <div className="grid grid-cols-2 gap-4">
                <Card>
                  <CardContent className="p-4">
                    <p className="text-sm text-muted-foreground mb-2">Time Remaining</p>
                    <CountdownTimer
                      expiresAt={group.expires_at}
                      timeRemainingSeconds={realtimeData?.time_remaining_seconds}
                      showBadge={false}
                    />
                  </CardContent>
                </Card>

                <Card>
                  <CardContent className="p-4">
                    <p className="text-sm text-muted-foreground mb-2">Participants</p>
                    <ParticipantsList
                      participantsCount={participantsCount}
                      showAnimation={true}
                      variant="inline"
                    />
                  </CardContent>
                </Card>
              </div>

              {/* Product Description */}
              <div>
                <h3 className="font-semibold mb-2">Product Details</h3>
                <p className="text-muted-foreground">{group.product.description}</p>
              </div>
            </CardContent>
          </Card>

          {/* Recent Activity Card */}
          {lastUpdate && (
            <Card className="border-green-200 bg-green-50">
              <CardHeader>
                <CardTitle className="text-sm flex items-center gap-2">
                  <CheckCircle className="h-4 w-4 text-green-600" />
                  Recent Activity
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm">
                  {lastUpdate.type === 'new_commitment' && (
                    <span>🎉 {lastUpdate.data.message}</span>
                  )}
                  {lastUpdate.type === 'threshold' && (
                    <span>🎯 {lastUpdate.data.message}</span>
                  )}
                  {lastUpdate.type === 'progress' && (
                    <span>📈 Progress updated to {lastUpdate.data.progress_percent.toFixed(1)}%</span>
                  )}
                </p>
              </CardContent>
            </Card>
          )}
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* Pricing Card */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Tag className="h-5 w-5" />
                Pricing
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Regular Price</span>
                  <span className="line-through">£{group.product.price}</span>
                </div>

                <div className="flex justify-between text-green-600 font-semibold">
                  <span>Group Price</span>
                  <span>£{discountedPrice.toFixed(2)}</span>
                </div>

                <div className="flex justify-between items-center pt-2 border-t">
                  <span className="font-medium">Savings</span>
                  <Badge className="bg-green-100 text-green-800">
                    £{savingsPerUnit.toFixed(2)} per unit ({group.discount_percent}%)
                  </Badge>
                </div>
              </div>

              {user ? (
                <Button
                  className="w-full"
                  size="lg"
                  onClick={() => setShowJoinModal(true)}
                  disabled={group.status !== 'open'}
                >
                  <Users className="h-4 w-4 mr-2" />
                  Join This Group
                </Button>
              ) : (
                <Button
                  className="w-full"
                  size="lg"
                  onClick={() => navigate('/login')}
                >
                  Login to Join
                </Button>
              )}

              {group.status !== 'open' && (
                <Alert>
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription className="text-xs">
                    This group is no longer accepting new participants.
                  </AlertDescription>
                </Alert>
              )}
            </CardContent>
          </Card>

          {/* Stats Card */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Target className="h-5 w-5" />
                Group Stats
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Current</span>
                <span className="font-medium">{currentQuantity} units</span>
              </div>

              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Target</span>
                <span className="font-medium">{targetQuantity} units</span>
              </div>

              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Minimum</span>
                <span className="font-medium">{group.min_quantity} units</span>
              </div>

              <div className="flex justify-between text-sm pt-2 border-t">
                <span className="text-muted-foreground">Stock Available</span>
                <span className="font-medium">{group.product.stock_quantity} units</span>
              </div>
            </CardContent>
          </Card>

          {/* Info Card */}
          <Alert>
            <Info className="h-4 w-4" />
            <AlertDescription className="text-xs">
              <strong>How it works:</strong> Your card will be pre-authorized when you join.
              Payment is only captured if the group reaches its minimum quantity before expiry.
            </AlertDescription>
          </Alert>
        </div>
      </div>

      {/* Join Modal */}
      {group && (
        <JoinGroupModal
          group={group}
          open={showJoinModal}
          onOpenChange={setShowJoinModal}
          onSuccess={() => {
            toast({
              title: 'Success!',
              description: 'You have joined the buying group.',
            });
          }}
        />
      )}
    </div>
  );
}