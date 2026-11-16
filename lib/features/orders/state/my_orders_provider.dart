import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client.dart';
import '../../../core/network/app_failure.dart';
import '../data/order_models.dart';
import '../data/orders_repository.dart';

final ordersRepositoryProvider = Provider<OrdersRepository>(
    (ref) => OrdersRepository(ref.watch(apiClientProvider)));

/// Loaded pages of My Orders. A failed refresh or page keeps [orders] and sets
/// [refreshFailed] (Req 15.9).
class MyOrdersState {
  const MyOrdersState({
    this.orders = const [],
    this.hasMore = false,
    this.refreshFailed = false,
    this.loadingMore = false,
  });

  final List<OrderSummary> orders;
  final bool hasMore;
  final bool refreshFailed;
  final bool loadingMore;

  MyOrdersState copyWith({
    List<OrderSummary>? orders,
    bool? hasMore,
    bool? refreshFailed,
    bool? loadingMore,
  }) =>
      MyOrdersState(
        orders: orders ?? this.orders,
        hasMore: hasMore ?? this.hasMore,
        refreshFailed: refreshFailed ?? this.refreshFailed,
        loadingMore: loadingMore ?? this.loadingMore,
      );
}

class MyOrdersNotifier extends AsyncNotifier<MyOrdersState> {
  // Auto-disposed with the screen, so reopening reloads (Req 15.8).
  @override
  Future<MyOrdersState> build() async {
    final page = await ref.read(ordersRepositoryProvider).list();
    return MyOrdersState(orders: page.items, hasMore: page.hasMore);
  }

  /// Reloads the first page. On failure the last data stays and
  /// [MyOrdersState.refreshFailed] is set; with no data the error is shown.
  Future<void> refresh() async {
    final previous = state.value;
    try {
      final page = await ref.read(ordersRepositoryProvider).list();
      state =
          AsyncData(MyOrdersState(orders: page.items, hasMore: page.hasMore));
    } on AppFailure catch (e, st) {
      if (previous == null) {
        state = AsyncError(e, st);
      } else {
        state = AsyncData(
            previous.copyWith(refreshFailed: true, loadingMore: false));
      }
    }
  }

  /// Retry from the error view (no data yet).
  Future<void> retry() async {
    if (state.hasValue) return refresh();
    state = const AsyncLoading();
    await refresh();
  }

  Future<void> loadMore() async {
    final current = state.value;
    if (current == null || !current.hasMore || current.loadingMore) return;
    state =
        AsyncData(current.copyWith(loadingMore: true, refreshFailed: false));
    try {
      final page = await ref
          .read(ordersRepositoryProvider)
          .list(offset: current.orders.length);
      state = AsyncData(MyOrdersState(
          orders: [...current.orders, ...page.items], hasMore: page.hasMore));
    } on AppFailure {
      state =
          AsyncData(current.copyWith(refreshFailed: true, loadingMore: false));
    }
  }
}

final myOrdersProvider =
    AsyncNotifierProvider.autoDispose<MyOrdersNotifier, MyOrdersState>(
        MyOrdersNotifier.new);

/// One order with the last data kept when a reload fails (Req 15.9).
class OrderDetailState {
  const OrderDetailState(this.order, {this.refreshFailed = false});
  final OrderDetail order;
  final bool refreshFailed;
}

class OrderDetailNotifier extends AsyncNotifier<OrderDetailState> {
  OrderDetailNotifier(this.orderId);
  final String orderId;

  @override
  Future<OrderDetailState> build() async =>
      OrderDetailState(await ref.read(ordersRepositoryProvider).get(orderId));

  Future<void> refresh() async {
    final previous = state.value;
    try {
      final order = await ref.read(ordersRepositoryProvider).get(orderId);
      state = AsyncData(OrderDetailState(order));
    } on AppFailure catch (e, st) {
      state = previous == null
          ? AsyncError(e, st)
          : AsyncData(OrderDetailState(previous.order, refreshFailed: true));
    }
  }

  Future<void> retry() async {
    if (!state.hasValue) state = const AsyncLoading();
    await refresh();
  }
}

/// Re-created each time the screen opens, so reopening reloads (Req 15.8).
final orderDetailProvider = AsyncNotifierProvider.autoDispose
    .family<OrderDetailNotifier, OrderDetailState, String>(
        OrderDetailNotifier.new);
