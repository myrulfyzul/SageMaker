import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client.dart';
import '../../../core/network/app_failure.dart';
import '../../auth/data/auth_user.dart';
import '../../auth/state/session_provider.dart';

/// One in-app notification (`GET /api/notifications`).
class AppNotification {
  const AppNotification({
    required this.id,
    required this.type,
    required this.title,
    required this.body,
    required this.isRead,
    this.createdAt,
  });

  factory AppNotification.fromJson(Map<String, dynamic> j) => AppNotification(
        id: (j['id'] as num).toInt(),
        type: (j['type'] ?? '').toString(),
        title: (j['title'] ?? '').toString(),
        body: (j['body'] ?? '').toString(),
        isRead: j['isRead'] == true,
        createdAt:
            DateTime.tryParse((j['createdAt'] ?? '').toString())?.toLocal(),
      );

  final int id;
  final String type;
  final String title;
  final String body;
  final bool isRead;
  final DateTime? createdAt;

  AppNotification asRead() => AppNotification(
      id: id,
      type: type,
      title: title,
      body: body,
      isRead: true,
      createdAt: createdAt);
}

class NotificationsPage {
  const NotificationsPage(this.items, this.unreadCount, this.total);
  final List<AppNotification> items;
  final int unreadCount;
  final int total;
}

class NotificationsRepository {
  NotificationsRepository(this._client);
  final ApiClient _client;

  Future<NotificationsPage> list({int limit = 20, int offset = 0}) async {
    final data = await _client
        .get('/api/notifications', query: {'limit': limit, 'offset': offset});
    final map = Map<String, dynamic>.from(data as Map);
    final items = [
      for (final i in (map['items'] as List? ?? const []))
        AppNotification.fromJson(Map<String, dynamic>.from(i as Map)),
    ];
    return NotificationsPage(
      items,
      (map['unreadCount'] as num?)?.toInt() ?? 0,
      (map['total'] as num?)?.toInt() ?? items.length,
    );
  }

  Future<int> markRead(int id) async {
    final data = await _client.post('/api/notifications/$id/read');
    return (data is Map ? (data['unreadCount'] as num?)?.toInt() : null) ?? 0;
  }

  Future<int> markAllRead() async {
    final data = await _client.post('/api/notifications/read-all');
    return (data is Map ? (data['unreadCount'] as num?)?.toInt() : null) ?? 0;
  }
}

final notificationsRepositoryProvider = Provider<NotificationsRepository>(
    (ref) => NotificationsRepository(ref.watch(apiClientProvider)));

class NotificationsState {
  const NotificationsState({
    this.items = const [],
    this.unreadCount = 0,
    this.total = 0,
    this.actionFailed = false,
  });

  final List<AppNotification> items;
  final int unreadCount;
  final int total;

  /// A mark-read call failed; the list is unchanged.
  final bool actionFailed;

  bool get hasMore => items.length < total;
}

class NotificationsNotifier extends AsyncNotifier<NotificationsState> {
  @override
  Future<NotificationsState> build() async {
    final p = await ref.read(notificationsRepositoryProvider).list();
    return NotificationsState(
        items: p.items, unreadCount: p.unreadCount, total: p.total);
  }

  Future<void> refresh() async {
    final previous = state.value;
    try {
      final p = await ref.read(notificationsRepositoryProvider).list();
      state = AsyncData(NotificationsState(
          items: p.items, unreadCount: p.unreadCount, total: p.total));
    } on AppFailure catch (e, st) {
      state = previous == null
          ? AsyncError(e, st)
          : AsyncData(NotificationsState(
              items: previous.items,
              unreadCount: previous.unreadCount,
              total: previous.total,
              actionFailed: true));
    }
  }

  Future<void> retry() async {
    if (!state.hasValue) state = const AsyncLoading();
    await refresh();
  }

  Future<void> loadMore() async {
    final c = state.value;
    if (c == null || !c.hasMore) return;
    try {
      final p = await ref
          .read(notificationsRepositoryProvider)
          .list(offset: c.items.length);
      state = AsyncData(NotificationsState(
          items: [...c.items, ...p.items],
          unreadCount: p.unreadCount,
          total: p.total));
    } on AppFailure {
      state = AsyncData(NotificationsState(
          items: c.items,
          unreadCount: c.unreadCount,
          total: c.total,
          actionFailed: true));
    }
  }

  Future<void> markRead(int id) async {
    final c = state.value;
    if (c == null) return;
    try {
      final unread =
          await ref.read(notificationsRepositoryProvider).markRead(id);
      state = AsyncData(NotificationsState(
          items: [for (final n in c.items) n.id == id ? n.asRead() : n],
          unreadCount: unread,
          total: c.total));
      ref.invalidate(unreadCountProvider);
    } on AppFailure {
      state = AsyncData(NotificationsState(
          items: c.items,
          unreadCount: c.unreadCount,
          total: c.total,
          actionFailed: true));
    }
  }

  Future<void> markAllRead() async {
    final c = state.value;
    if (c == null) return;
    try {
      final unread =
          await ref.read(notificationsRepositoryProvider).markAllRead();
      state = AsyncData(NotificationsState(
          items: [for (final n in c.items) n.asRead()],
          unreadCount: unread,
          total: c.total));
      ref.invalidate(unreadCountProvider);
    } on AppFailure {
      state = AsyncData(NotificationsState(
          items: c.items,
          unreadCount: c.unreadCount,
          total: c.total,
          actionFailed: true));
    }
  }
}

final notificationsProvider = AsyncNotifierProvider.autoDispose<
    NotificationsNotifier, NotificationsState>(NotificationsNotifier.new);

/// Unread count for the badge. 0 when signed out, for an artisan (who has no
/// notifications) or when the call fails. Show it with `BadgeCount`, which
/// renders `1` to `99` and then `99+` (Req 17.9).
final unreadCountProvider = FutureProvider.autoDispose<int>((ref) async {
  final session = ref.watch(sessionProvider);
  if (session is! SessionSignedIn || session.role == AppRole.artisan) return 0;
  try {
    final p = await ref
        .read(notificationsRepositoryProvider)
        .list(limit: 1, offset: 0);
    return p.unreadCount;
  } on AppFailure {
    return 0;
  }
});
