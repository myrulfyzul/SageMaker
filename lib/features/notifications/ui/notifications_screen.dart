import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/widgets/async_value_view.dart';
import '../../../core/widgets/badge_count.dart';
import '../../../core/widgets/empty_view.dart';
import '../../../core/widgets/error_view.dart';
import '../../../core/widgets/loading_view.dart';
import '../../orders/data/order_models.dart';
import '../state/notifications_provider.dart';

/// Notifications list: newest first, tap to mark read, mark all read, and a
/// `99+` unread badge (Req 17.6, 17.7, 17.9, 17.10).
class NotificationsScreen extends ConsumerWidget {
  const NotificationsScreen({super.key});

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
            padding: EdgeInsets.only(right: 12),
            child: Text('Notifications'),
          ),
        ),
        actions: [
          TextButton(
            onPressed: unread > 0 ? notifier.markAllRead : null,
            child: const Text('Mark all read'),
          ),
        ],
      ),
      body: _body(context, value, notifier),
    );
  }

  Widget _body(BuildContext context, AsyncValue<NotificationsState> value,
      NotificationsNotifier notifier) {
    if (!value.hasValue) {
      if (value.hasError) {
        return ErrorView(
            message: AsyncValueView.defaultErrorMessage(value.error!),
            onRetry: notifier.retry);
      }
      return const LoadingView();
    }
    final s = value.requireValue;
    if (s.items.isEmpty) {
      return EmptyView(
        message: 'You have no notifications.',
        actionLabel: 'Explore products',
        onAction: () => context.go('/shop'),
      );
    }
    return Column(
      children: [
        if (s.actionFailed)
          MaterialBanner(
            content: const Text('That did not work. Please try again.'),
            actions: [
              TextButton(onPressed: notifier.refresh, child: const Text('Retry')),
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
                            fontWeight:
                                n.isRead ? FontWeight.w400 : FontWeight.w700)),
                    subtitle: Text([
                      if (n.body.isNotEmpty) n.body,
                      if (n.createdAt != null) formatLocalDateTime(n.createdAt!),
                    ].join('\n')),
                    isThreeLine: n.body.isNotEmpty && n.createdAt != null,
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
      ],
    );
  }
}
