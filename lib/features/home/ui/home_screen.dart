import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/widgets/async_value_view.dart';
import '../../../core/widgets/demo_label.dart';
import '../../catalogue/data/catalogue_models.dart';
import '../../catalogue/state/shop_provider.dart';
import '../../catalogue/ui/product_card.dart';

/// Returns the trimmed search text when it is 1 to 100 characters, else null
/// (Req 8.6, 8.7).
String? validHomeSearch(String raw) {
  final t = raw.trim();
  return t.isEmpty || t.length > 100 ? null : t;
}

/// Home (Req 8.1). Each product section loads and retries independently.
class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key, this.onSearch});

  /// Called with a valid query; defaults to opening Shop with `?q=`.
  final void Function(BuildContext context, String query)? onSearch;

  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen> {
  final _controller = TextEditingController();
  final _focus = FocusNode();

  @override
  void dispose() {
    _controller.dispose();
    _focus.dispose();
    super.dispose();
  }

  void _submit(String raw) {
    final q = validHomeSearch(raw);
    if (q == null) {
      // Stay on Home and keep the field focused (Req 8.7).
      _focus.requestFocus();
      return;
    }
    final cb = widget.onSearch;
    if (cb != null) {
      cb(context, q);
    } else {
      context.go(Uri(path: '/shop', queryParameters: {'q': q}).toString());
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('Sagemaker')),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        TextField(
          key: const Key('home-search'),
          controller: _controller,
          focusNode: _focus,
          maxLength: 100,
          textInputAction: TextInputAction.search,
          decoration: InputDecoration(
            hintText: 'Search products',
            counterText: '',
            prefixIcon: const Icon(Icons.search),
            suffixIcon: IconButton(
              tooltip: 'Search',
              icon: const Icon(Icons.arrow_forward),
              onPressed: () => _submit(_controller.text),
            ),
          ),
          onSubmitted: _submit,
        ),
        const SizedBox(height: 16),
        _Banner(onShop: () => context.go('/shop')),
        const SizedBox(height: 20),
        Text('Collections', style: theme.textTheme.titleMedium),
        const SizedBox(height: 8),
        Wrap(spacing: 8, runSpacing: 8, children: [
          for (final (label, icon) in const [
            ('Heritage Totebags', Icons.shopping_bag_outlined),
            ('Kids & Toys', Icons.toys_outlined),
            ('Lifestyle', Icons.auto_awesome_outlined),
          ])
            ActionChip(
                avatar: Icon(icon, size: 18),
                label: Text(label),
                onPressed: () => context.go('/shop')),
        ]),
        const SizedBox(height: 20),
        Text('Categories', style: theme.textTheme.titleMedium),
        const SizedBox(height: 8),
        _Categories(),
        const SizedBox(height: 20),
        _ProductSection(title: 'Best sellers', provider: bestSellersProvider),
        _ProductSection(title: 'New arrivals', provider: newArrivalsProvider),
        _ProductSection(
            title: 'Recommended for you', provider: recommendationsProvider),
        const SizedBox(height: 8),
        Card(
          child: ListTile(
            leading: const Icon(Icons.favorite_outline),
            title: const Text('More than a purchase'),
            subtitle: const Text(
                'Every piece supports creative women artisans. Learn their story.'),
            trailing: const Icon(Icons.north_east),
            onTap: () => context.push('/about'),
          ),
        ),
      ]),
    );
  }
}

class _Banner extends StatelessWidget {
  const _Banner({required this.onShop});
  final VoidCallback onShop;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
          color: scheme.primary, borderRadius: BorderRadius.circular(16)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('Shop with impact. Carry a story.',
            style: Theme.of(context)
                .textTheme
                .headlineSmall
                ?.copyWith(color: scheme.onPrimary)),
        const SizedBox(height: 8),
        Text(
            'Handcrafted gifts and everyday essentials celebrating culture, creativity and women artisans.',
            style: TextStyle(color: scheme.onPrimary)),
        const SizedBox(height: 12),
        const DemoLabel.prototype(),
        const SizedBox(height: 12),
        FilledButton(
            style: FilledButton.styleFrom(
                backgroundColor: scheme.tertiary,
                foregroundColor: scheme.onTertiary),
            onPressed: onShop,
            child: const Text('Explore our collection')),
      ]),
    );
  }
}

class _Categories extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final value = ref.watch(categoriesProvider);
    return value.when(
      loading: () => const Padding(
          padding: EdgeInsets.all(8),
          child: Center(child: CircularProgressIndicator(semanticsLabel: 'Loading'))),
      error: (e, _) => _SectionError(
          message: AsyncValueView.defaultErrorMessage(e),
          onRetry: () => ref.invalidate(categoriesProvider)),
      data: (cats) => cats.isEmpty
          ? const Text('No categories yet.')
          : Wrap(spacing: 8, runSpacing: 8, children: [
              for (final c in cats)
                ActionChip(
                  label: Text(c.name),
                  onPressed: () => context.go(Uri(
                      path: '/shop',
                      queryParameters: {'category': c.slug}).toString()),
                ),
            ]),
    );
  }
}

class _ProductSection extends ConsumerWidget {
  const _ProductSection({required this.title, required this.provider});
  final String title;
  final FutureProvider<List<CatalogueProduct>> provider;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final value = ref.watch(provider);
    return Padding(
      padding: const EdgeInsets.only(bottom: 20),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(title, style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        value.when(
          loading: () => const SizedBox(
              height: 80,
              child: Center(
                  child: CircularProgressIndicator(semanticsLabel: 'Loading'))),
          error: (e, _) => _SectionError(
              message: AsyncValueView.defaultErrorMessage(e),
              onRetry: () => ref.invalidate(provider)),
          data: (items) => items.isEmpty
              ? _SectionError(
                  message: 'Nothing to show here yet.',
                  onRetry: () => ref.invalidate(provider))
              : SizedBox(
                  height: 290,
                  child: ListView.separated(
                    scrollDirection: Axis.horizontal,
                    itemCount: items.length,
                    separatorBuilder: (_, __) => const SizedBox(width: 12),
                    itemBuilder: (_, i) => SizedBox(
                      width: 190,
                      child: ProductCard(
                        product: items[i],
                        onTap: () => context.push('/product/${items[i].id}'),
                      ),
                    ),
                  ),
                ),
        ),
      ]),
    );
  }
}

class _SectionError extends StatelessWidget {
  const _SectionError({required this.message, required this.onRetry});
  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) => Row(children: [
        const Icon(Icons.info_outline, semanticLabel: 'Notice'),
        const SizedBox(width: 8),
        Expanded(child: Text(message)),
        TextButton(onPressed: onRetry, child: const Text('Retry')),
      ]);
}
