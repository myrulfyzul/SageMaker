import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/widgets/async_value_view.dart';
import '../../../core/widgets/empty_view.dart';
import '../../../core/widgets/error_view.dart';
import '../../../core/widgets/loading_view.dart';
import '../data/catalogue_models.dart';
import '../state/shop_provider.dart';
import 'product_card.dart';

/// Shop: search, category filter, price sort and paging (Req 9.2 to 9.8).
class ShopScreen extends ConsumerStatefulWidget {
  const ShopScreen({super.key, this.initialQuery, this.initialCategory});
  final String? initialQuery;
  final String? initialCategory;

  @override
  ConsumerState<ShopScreen> createState() => _ShopScreenState();
}

class _ShopScreenState extends ConsumerState<ShopScreen> {
  late final TextEditingController _search;
  final _scroll = ScrollController();

  @override
  void initState() {
    super.initState();
    _search = TextEditingController(text: widget.initialQuery ?? '');
    _scroll.addListener(() {
      if (_scroll.position.extentAfter < 300) {
        ref.read(shopProvider.notifier).loadMore();
      }
    });
    final q = _search.text.trim();
    Future.microtask(() => ref.read(shopProvider.notifier).load(ShopQuery(
        q: q.length > 100 ? q.substring(0, 100) : q,
        category: widget.initialCategory)));
  }

  @override
  void didUpdateWidget(ShopScreen old) {
    super.didUpdateWidget(old);
    if (widget.initialQuery != old.initialQuery ||
        widget.initialCategory != old.initialCategory) {
      final q = (widget.initialQuery ?? '').trim();
      _search.text = q;
      _apply(ShopQuery(q: q, category: widget.initialCategory));
    }
  }

  @override
  void dispose() {
    _search.dispose();
    _scroll.dispose();
    super.dispose();
  }

  void _apply(ShopQuery q) => ref.read(shopProvider.notifier).load(q);

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(shopProvider);
    final categories = ref.watch(categoriesProvider);
    final query = state.query;
    return Scaffold(
      appBar: AppBar(title: const Text('Shop')),
      body: Column(children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
          child: TextField(
            controller: _search,
            maxLength: 100,
            textInputAction: TextInputAction.search,
            decoration: const InputDecoration(
                hintText: 'Search products',
                prefixIcon: Icon(Icons.search),
                counterText: ''),
            onSubmitted: (v) => _apply(query.copyWith(q: v.trim())),
          ),
        ),
        SizedBox(
          height: 48,
          child: ListView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 12),
            children: [
              _chip('All', query.category == null,
                  () => _apply(query.copyWith(clearCategory: true))),
              for (final c in categories.value ?? const <CategoryRef>[])
                _chip(c.name, query.category == c.slug,
                    () => _apply(query.copyWith(category: c.slug))),
              const SizedBox(width: 8),
              _chip('Price: low to high', query.sort == 'price_asc', () {
                _apply(query.sort == 'price_asc'
                    ? query.copyWith(clearSort: true)
                    : query.copyWith(sort: 'price_asc'));
              }),
              _chip('Price: high to low', query.sort == 'price_desc', () {
                _apply(query.sort == 'price_desc'
                    ? query.copyWith(clearSort: true)
                    : query.copyWith(sort: 'price_desc'));
              }),
            ],
          ),
        ),
        Expanded(child: _body(state)),
      ]),
    );
  }

  Widget _chip(String label, bool selected, VoidCallback onTap) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 6),
        child: ChoiceChip(
            label: Text(label), selected: selected, onSelected: (_) => onTap()),
      );

  Widget _body(ShopState state) {
    if (state.loading && state.items.isEmpty) return const LoadingView();
    if (state.error != null) {
      return ErrorView(
          message: AsyncValueView.defaultErrorMessage(state.error!),
          onRetry: () => ref.read(shopProvider.notifier).retry());
    }
    if (state.items.isEmpty) {
      return EmptyView(
        message: 'No matching products.',
        actionLabel: 'Clear filters',
        onAction: () {
          _search.clear();
          _apply(const ShopQuery());
        },
      );
    }
    return LayoutBuilder(builder: (context, c) {
      final cols = c.maxWidth < 530 ? 2 : (c.maxWidth < 850 ? 3 : 4);
      return CustomScrollView(controller: _scroll, slivers: [
        SliverPadding(
          padding: const EdgeInsets.all(16),
          sliver: SliverGrid.builder(
            itemCount: state.items.length,
            gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: cols,
                mainAxisExtent: 290,
                crossAxisSpacing: 12,
                mainAxisSpacing: 12),
            itemBuilder: (_, i) => ProductCard(
              product: state.items[i],
              onTap: () => context.push('/product/${state.items[i].id}'),
            ),
          ),
        ),
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.only(bottom: 16),
            child: state.loadingMore
                ? const LoadingView()
                : state.moreError != null
                    ? ErrorView(
                        message: AsyncValueView.defaultErrorMessage(
                            state.moreError!),
                        onRetry: () =>
                            ref.read(shopProvider.notifier).loadMore())
                    : state.hasMore
                        ? Center(
                            child: TextButton(
                                onPressed: () =>
                                    ref.read(shopProvider.notifier).loadMore(),
                                child: const Text('Load more')))
                        : const SizedBox.shrink(),
          ),
        ),
      ]);
    });
  }
}
