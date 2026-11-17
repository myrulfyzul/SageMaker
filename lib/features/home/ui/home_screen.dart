import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../app/theme.dart';
import '../../../core/widgets/async_value_view.dart';
import '../../../core/widgets/sagemaker_logo.dart';
import '../../../core/widgets/ui_kit.dart';
import '../../auth/state/session_provider.dart';
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
    final session = ref.watch(sessionProvider);
    final first = session is SessionSignedIn
        ? session.user.name.trim().split(' ').first
        : '';
    final name = first.isEmpty ? null : first;
    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: ListView(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
            children: [
              _Header(name: name),
              const SizedBox(height: 14),
              _SearchBar(
                  controller: _controller, focus: _focus, onSubmit: _submit),
              const SizedBox(height: 18),
              const _HeroCarousel(),
              const SizedBox(height: 24),
              const SectionHeader('Categories'),
              const _Categories(),
              const SizedBox(height: 24),
              _ProductSection(
                  title: 'Best sellers', provider: bestSellersProvider),
              _ProductSection(
                  title: 'New arrivals', provider: newArrivalsProvider),
              _ProductSection(
                  title: 'Recommended for you',
                  provider: recommendationsProvider),
              const _ImpactCard(),
            ]),
      ),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.name});
  final String? name;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Row(children: [
      Expanded(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const SageMakerLogo(height: 38),
          const SizedBox(height: 4),
          Text(name == null ? 'Selamat datang' : 'Hi, $name',
              style: theme.textTheme.bodySmall),
        ]),
      ),
      IconButton.filledTonal(
        tooltip: 'Notifications',
        style: IconButton.styleFrom(backgroundColor: kCard),
        onPressed: () => context.push('/notifications'),
        icon: const Icon(Icons.notifications_none_rounded),
      ),
    ]);
  }
}

class _SearchBar extends StatelessWidget {
  const _SearchBar(
      {required this.controller, required this.focus, required this.onSubmit});
  final TextEditingController controller;
  final FocusNode focus;
  final ValueChanged<String> onSubmit;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(999),
        boxShadow: softShadow(),
      ),
      child: TextField(
        key: const Key('home-search'),
        controller: controller,
        focusNode: focus,
        maxLength: 100,
        textInputAction: TextInputAction.search,
        decoration: InputDecoration(
          hintText: 'Search totes, toys, gifts...',
          counterText: '',
          prefixIcon: const Icon(Icons.search_rounded),
          border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(999),
              borderSide: BorderSide.none),
          enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(999),
              borderSide: BorderSide.none),
          focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(999),
              borderSide: const BorderSide(color: kPrimary, width: 1.5)),
          suffixIcon: Padding(
            padding: const EdgeInsets.all(6),
            child: IconButton.filled(
              tooltip: 'Search',
              icon: const Icon(Icons.arrow_forward_rounded, size: 20),
              onPressed: () => onSubmit(controller.text),
            ),
          ),
        ),
        onSubmitted: onSubmit,
      ),
    );
  }
}

class _Slide {
  const _Slide(this.tag, this.title, this.body, this.cta, this.icon,
      this.gradient, this.path);
  final String tag;
  final String title;
  final String body;
  final String cta;
  final IconData icon;
  final Gradient gradient;
  final String path;
}

const _slides = [
  _Slide(
      'HANDCRAFTED IN MALAYSIA',
      'Shop with impact. Carry a story.',
      'Gifts and everyday essentials made by women artisans.',
      'Explore our collection',
      Icons.shopping_bag_outlined,
      kHeroGradient,
      '/shop'),
  _Slide(
      'MADE FOR YOU',
      'Your idea, sewn by hand.',
      'Request a custom tote, fabric book or corporate gift.',
      'Start a custom order',
      Icons.design_services_outlined,
      LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF6B2E1F), Color(0xFFB4533A), kCoral]),
      '/custom-orders/new'),
  _Slide(
      'FOR LITTLE ONES',
      'Soft books & toys.',
      'Safe, washable fabric play for curious minds.',
      'Shop kids & toys',
      Icons.toys_outlined,
      LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF2B3A67), Color(0xFF4A5FA0), Color(0xFF7D8FD1)]),
      '/shop'),
];

class _HeroCarousel extends StatefulWidget {
  const _HeroCarousel();

  @override
  State<_HeroCarousel> createState() => _HeroCarouselState();
}

class _HeroCarouselState extends State<_HeroCarousel> {
  final _page = PageController(viewportFraction: 0.94);
  int _index = 0;

  @override
  void dispose() {
    _page.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(children: [
      SizedBox(
        height: 232,
        child: PageView.builder(
          controller: _page,
          padEnds: false,
          itemCount: _slides.length,
          onPageChanged: (i) => setState(() => _index = i),
          itemBuilder: (context, i) {
            final s = _slides[i];
            return Padding(
              padding: const EdgeInsets.only(right: 10),
              child: GradientPanel(
                gradient: s.gradient,
                child: Row(children: [
                  Expanded(
                    // Text on top, button at the bottom; fixed line limits so
                    // nothing is cut mid-line on small phones.
                    child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Column(
                            mainAxisSize: MainAxisSize.min,
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(s.tag,
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: const TextStyle(
                                      color: kAccent,
                                      fontSize: 11,
                                      letterSpacing: 1.2,
                                      fontWeight: FontWeight.w800)),
                              const SizedBox(height: 6),
                              Text(s.title,
                                  maxLines: 2,
                                  overflow: TextOverflow.ellipsis,
                                  style: const TextStyle(
                                      fontFamily: kDisplayFont,
                                      color: Colors.white,
                                      fontSize: 21,
                                      height: 1.15,
                                      fontWeight: FontWeight.w700)),
                              const SizedBox(height: 6),
                              Text(s.body,
                                  maxLines: 2,
                                  overflow: TextOverflow.ellipsis,
                                  style: const TextStyle(
                                      color: Colors.white70,
                                      fontSize: 12.5,
                                      height: 1.35)),
                            ],
                          ),
                          FilledButton(
                            style: FilledButton.styleFrom(
                              backgroundColor: kAccent,
                              foregroundColor: kText,
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 16, vertical: 10),
                              textStyle: const TextStyle(
                                  fontFamily: kBodyFont,
                                  fontWeight: FontWeight.w800,
                                  fontSize: 13),
                            ),
                            onPressed: () => s.path == '/shop'
                                ? context.go(s.path)
                                : context.push(s.path),
                            child: Text(s.cta),
                          ),
                        ]),
                  ),
                  const SizedBox(width: 8),
                  Icon(s.icon,
                      size: 64, color: Colors.white.withValues(alpha: 0.85)),
                ]),
              ),
            );
          },
        ),
      ),
      const SizedBox(height: 10),
      Row(mainAxisAlignment: MainAxisAlignment.center, children: [
        for (var i = 0; i < _slides.length; i++)
          AnimatedContainer(
            duration: const Duration(milliseconds: 250),
            margin: const EdgeInsets.symmetric(horizontal: 3),
            width: i == _index ? 22 : 7,
            height: 7,
            decoration: BoxDecoration(
              color: i == _index ? kPrimary : const Color(0xFFD9D1C3),
              borderRadius: BorderRadius.circular(99),
            ),
          ),
      ]),
    ]);
  }
}

IconData _categoryIcon(String slug) {
  final s = slug.toLowerCase();
  if (s.contains('tote') || s.contains('bag')) {
    return Icons.shopping_bag_outlined;
  }
  if (s.contains('book')) return Icons.menu_book_outlined;
  if (s.contains('toy') || s.contains('kid')) return Icons.toys_outlined;
  if (s.contains('gift')) return Icons.card_giftcard_outlined;
  if (s.contains('access')) return Icons.diamond_outlined;
  return Icons.auto_awesome_outlined;
}

class _Categories extends ConsumerWidget {
  const _Categories();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final value = ref.watch(categoriesProvider);
    return value.when(
      loading: () => SizedBox(
        height: 92,
        child: Row(children: [
          for (var i = 0; i < 4; i++)
            const Padding(
              padding: EdgeInsets.only(right: 12),
              child: SkeletonBox(width: 72, height: 88, radius: 20),
            ),
        ]),
      ),
      error: (e, _) => _SectionError(
          message: AsyncValueView.defaultErrorMessage(e),
          onRetry: () => ref.invalidate(categoriesProvider)),
      data: (cats) => cats.isEmpty
          ? const Text('No categories yet.')
          : SizedBox(
              height: 96,
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                itemCount: cats.length,
                separatorBuilder: (_, __) => const SizedBox(width: 12),
                itemBuilder: (_, i) {
                  final c = cats[i];
                  return FadeSlideIn(
                    index: i,
                    child: PressableScale(
                      onTap: () => context.go(Uri(
                          path: '/shop',
                          queryParameters: {'category': c.slug}).toString()),
                      child: SizedBox(
                        width: 78,
                        child: Column(children: [
                          Container(
                            width: 62,
                            height: 62,
                            decoration: BoxDecoration(
                              color: kCard,
                              borderRadius: BorderRadius.circular(20),
                              boxShadow: softShadow(),
                            ),
                            child: Icon(_categoryIcon(c.slug),
                                color: kPrimary, size: 28),
                          ),
                          const SizedBox(height: 6),
                          Text(c.name,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                  fontSize: 12, fontWeight: FontWeight.w600)),
                        ]),
                      ),
                    ),
                  );
                },
              ),
            ),
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
      padding: const EdgeInsets.only(bottom: 24),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SectionHeader(title,
            action: 'See all', onAction: () => context.go('/shop')),
        value.when(
          loading: () => SizedBox(
            height: 290,
            child: Row(children: const [
              Expanded(child: SkeletonBox(height: 290, radius: kRadiusLarge)),
              SizedBox(width: 12),
              Expanded(child: SkeletonBox(height: 290, radius: kRadiusLarge)),
            ]),
          ),
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
                    clipBehavior: Clip.none,
                    itemCount: items.length,
                    separatorBuilder: (_, __) => const SizedBox(width: 12),
                    itemBuilder: (_, i) => FadeSlideIn(
                      index: i,
                      child: SizedBox(
                        width: 190,
                        child: ProductCard(
                          product: items[i],
                          onTap: () => context.push('/product/${items[i].id}'),
                        ),
                      ),
                    ),
                  ),
                ),
        ),
      ]),
    );
  }
}

class _ImpactCard extends StatelessWidget {
  const _ImpactCard();

  @override
  Widget build(BuildContext context) {
    return PressableScale(
      onTap: () => context.push('/about'),
      child: GradientPanel(
        gradient: kGoldGradient,
        child: Row(children: [
          const Icon(Icons.volunteer_activism_outlined, size: 44, color: kText),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: const [
                  Text('More than a purchase',
                      style: TextStyle(
                          fontFamily: kDisplayFont,
                          fontSize: 20,
                          fontWeight: FontWeight.w700,
                          color: kText)),
                  SizedBox(height: 4),
                  Text(
                      'Every piece supports creative women artisans. Learn their story.',
                      style: TextStyle(color: kText, fontSize: 13)),
                ]),
          ),
          const Icon(Icons.north_east_rounded, color: kText),
        ]),
      ),
    );
  }
}

class _SectionError extends StatelessWidget {
  const _SectionError({required this.message, required this.onRetry});
  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) => SoftCard(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
        child: Row(children: [
          const Icon(Icons.info_outline,
              semanticLabel: 'Notice', color: kMuted),
          const SizedBox(width: 8),
          Expanded(child: Text(message)),
          TextButton(onPressed: onRetry, child: const Text('Retry')),
        ]),
      );
}
