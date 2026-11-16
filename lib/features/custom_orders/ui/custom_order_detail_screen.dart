import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/money.dart';
import '../../../core/network/api_client.dart';
import '../../../core/widgets/async_value_view.dart';
import '../../../core/widgets/error_view.dart';
import '../../../core/widgets/loading_view.dart';
import '../data/custom_order_models.dart';
import '../state/custom_orders_provider.dart';

/// One custom order with the quoted price or the rejection reason (Req 16.6).
class CustomOrderDetailScreen extends ConsumerWidget {
  const CustomOrderDetailScreen({super.key, required this.orderId});

  final int orderId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final value = ref.watch(customOrderDetailProvider(orderId));
    return Scaffold(
      appBar: AppBar(title: const Text('Custom order')),
      body: value.when(
        loading: () => const LoadingView(),
        error: (e, _) => ErrorView(
            message: AsyncValueView.defaultErrorMessage(e),
            onRetry: () => ref.invalidate(customOrderDetailProvider(orderId))),
        data: (o) => _Body(order: o),
      ),
    );
  }
}

class _Body extends ConsumerWidget {
  const _Body({required this.order});
  final CustomOrder order;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final price = order.estimatedPriceSen;
    final reason = order.rejectReason;
    final scheme = Theme.of(context).colorScheme;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text(order.productType,
            style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 8),
        Chip(label: Text(customOrderStatusLabel(order.status))),
        const SizedBox(height: 12),
        Text('Quantity: ${order.quantity}'),
        Text('Preferred date: ${order.preferredDate}'),
        const SizedBox(height: 12),
        Text(order.description),
        if (price != null) ...[
          const SizedBox(height: 16),
          Text('Quoted price: ${formatRm(price)}',
              key: const ValueKey('quoted-price'),
              style: const TextStyle(fontWeight: FontWeight.w700)),
        ],
        if (order.status == 'rejected' && reason != null) ...[
          const SizedBox(height: 16),
          Text('Rejection reason: $reason',
              key: const ValueKey('reject-reason'),
              style: TextStyle(color: scheme.error)),
        ],
        if (order.imageUrls.isNotEmpty) ...[
          const SizedBox(height: 16),
          const Text('Reference images',
              style: TextStyle(fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          Wrap(spacing: 8, runSpacing: 8, children: [
            for (final u in order.imageUrls) AuthImage(path: u, size: 96),
          ]),
        ],
      ],
    );
  }
}

/// Loads `/api/media/{filename}` with the Bearer token from [ApiClient].
class AuthImage extends ConsumerWidget {
  const AuthImage({super.key, required this.path, required this.size});

  final String path;
  final double size;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final client = ref.watch(apiClientProvider);
    final token = client.token;
    return SizedBox(
      width: size,
      height: size,
      child: Image.network(
        client.uri(path).toString(),
        headers: {if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token'},
        fit: BoxFit.cover,
        semanticLabel: 'Reference image',
        errorBuilder: (_, __, ___) =>
            const Icon(Icons.broken_image_outlined, semanticLabel: 'Image unavailable'),
      ),
    );
  }
}
