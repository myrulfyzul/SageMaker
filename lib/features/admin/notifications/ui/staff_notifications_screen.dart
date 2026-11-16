import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/widgets/async_value_view.dart';
import '../../../../core/widgets/badge_count.dart';
import '../../../../core/widgets/empty_view.dart';
import '../../../../core/widgets/error_view.dart';
import '../../../../core/widgets/loading_view.dart';
import '../../../notifications/state/notifications_provider.dart';
import '../../../orders/data/order_models.dart';

/// Staff notifications (Req 17.6): same data as the customer list, with a
/// staff empty state (no storefront link) and a `99+` unread badge.
class StaffNotificationsScreen extends ConsumerWidget {
  const StaffNotificationsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final value = ref.watch(notificationsProvider);
    final notifier = ref.read(notificationsProvider.notifier);
    final unread = value.value?.unreadCount ?? 0;
    return Scaffold(
      appBar: AppBar(
        title: BadgeCount(
          count: unread,
          child: const Padding(
              padding: EdgeInsets.only(right: 12), child: Text('Notifications')),
        ),
        actions: [
          TextButton(
            onPressed: unread > 0 ? notifier.markAllRead : null,
            child: const Text('Mark all read'),
          ),
        ],
      ),
      body: _body(value, notifier),
    );
  }

  Widget _body(
      AsyncValue<NotificationsState> value, NotificationsNotifier notifier) {
    if (!value.hasValue) {
      return value.hasError
          ? ErrorView(
              message: AsyncValueView.defaultErrorMessage(value.error!),
              onRetry: notifier.retry)
          : const LoadingView();
    }
    final s = value.requireValue;
    if (s.items.isEmpty) {
      return EmptyView(
          message: 'You have no notifications.',
          actionLabel: 'Refresh',
          onAction: notifier.refresh);
    }
    return Column(children: [
      if (s.actionFailed)
        MaterialBanner(
          content: const Text('That did not work. Please try again.'),
          actions: [
            TextButton(onPressed: notifier.refresh, child: const Text('Retry'))
          ],
        ),
      Expanded(
        child: RefreshIndicator(
          onRefresh: notifier.refresh,
          child: ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            children: [
              for (final n in s.items)
                ListTile(
                  key: ValueKey('notification-${n.id}'),
                  leading: Icon(
                      n.isRead
                          ? Icons.notifications_none
                          : Icons.notifications_active,
                      semanticLabel: n.isRead ? 'Read' : 'Unread'),
                  title: Text(n.title,
                      style: TextStyle(
                          fontWeight: n.isRead ? FontWeight.w400 : FontWeight.w700)),
                  subtitle: Text([
                    if (n.body.isNotEmpty) n.body,
                    if (n.createdAt != null) formatLocalDateTime(n.createdAt!),
                  ].join('\n')),
                  onTap: n.isRead ? null : () => notifier.markRead(n.id),
                ),
              if (s.hasMore)
                Padding(
                  padding: const EdgeInsets.all(12),
                  child: OutlinedButton(
                      onPressed: notifier.loadMore,
                      child: const Text('Load more')),
                ),
            ],
          ),
        ),
      ),
    ]);
  }
}
