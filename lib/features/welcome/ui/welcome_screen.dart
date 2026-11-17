import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../app/theme.dart';
import '../../../core/widgets/sagemaker_logo.dart';
import '../../../core/widgets/ui_kit.dart';
import '../../../core/widgets/vimeo_player.dart';

/// Content from www.sagemaker.asia (home page, November 2026).
abstract final class SagemakerSite {
  static const url = 'https://www.sagemaker.asia/';
  static const contactUrl = 'https://www.sagemaker.asia/contact/';
  static const videoId = '1242530739';
  static const _uploads =
      'https://www.sagemaker.asia/wp-content/uploads/2026/11';
  static const heroImage = '$_uploads/GAP06537-2-1024x683.jpg';
  static const storyImage = '$_uploads/GAP05225-1-683x1024.jpg';
  static const communityImage =
      '$_uploads/Your-Purposeful-Project-Powered-by-the-Community-1-768x530.png';

  static const tagline = 'Stitches of Strength, Stories of Wonder';
  static const intro =
      'We connect businesses to local makers, turning creative capabilities into '
      'meaningful products, commercial opportunities and sustainable livelihoods.';

  static const pillars = [
    (
      Icons.school_outlined,
      'We develop.',
      'Building capabilities that open doors.',
      'We support local makers in strengthening their technical skills, business '
          'knowledge and production readiness, helping them prepare for real '
          'commercial opportunities.'
    ),
    (
      Icons.hub_outlined,
      'We connect.',
      'Bringing local talent closer to the market.',
      'We connect businesses with local makers through product development, '
          'customised solutions and commercial production opportunities.'
    ),
    (
      Icons.precision_manufacturing_outlined,
      'We enable.',
      'Making local production work together.',
      'We organise and coordinate distributed production through product '
          'specifications, production planning, quality standards and systems '
          'that help makers fulfil business needs.'
    ),
  ];

  /// (target number, suffix, label)
  static const impact = [
    (120, '', 'Makers trained'),
    (44, '', 'Makers onboarded'),
    (90, 'K+', 'Income distributed'),
    (4000, '+', 'Pieces handcrafted'),
  ];

  static const accessTitle = 'Talent is not the problem. Access is.';
  static const accessBody = [
    'Across local communities, there are people with valuable skills, creativity '
        'and the ability to make things.',
    'For many women, especially those balancing family and caregiving '
        'responsibilities, home-based enterprises offer a way to participate in '
        'the economy while managing responsibilities at home.',
    'But having the skills to make something doesn’t always mean having access '
        'to a sustainable livelihood. Limited market access, inconsistent orders, '
        'production resources and business support can make it difficult for '
        'small makers to grow beyond individual orders.',
  ];

  static const partners = [
    (
      Icons.business_center_outlined,
      'Commercial partner',
      'Have a product idea, project or production need?'
    ),
    (
      Icons.volunteer_activism_outlined,
      'Impact partners',
      'Want to empower community with new economic opportunities?'
    ),
    (
      Icons.storefront_outlined,
      'Local makers',
      'Have your own makers hub and want to amplify your growth?'
    ),
  ];
}

Future<void> _open(String url) =>
    launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);

/// Landing page shown when the app opens (signed out) and from Profile.
class WelcomeScreen extends StatelessWidget {
  const WelcomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: CustomScrollView(slivers: [
        const SliverToBoxAdapter(child: _Hero()),
        SliverPadding(
          padding: const EdgeInsets.fromLTRB(16, 24, 16, 32),
          sliver: SliverList.list(children: const [
            _VideoSection(),
            SizedBox(height: 32),
            _PillarsSection(),
            SizedBox(height: 28),
            _ImpactSection(),
            SizedBox(height: 32),
            _AccessSection(),
            SizedBox(height: 32),
            _PartnersSection(),
            SizedBox(height: 28),
            _BottomCta(),
          ]),
        ),
      ]),
    );
  }
}

/// Network photo from the SageMaker site with a gradient fallback.
class _SiteImage extends StatelessWidget {
  const _SiteImage(this.url);
  final String url;

  @override
  Widget build(BuildContext context) => Image.network(
        url,
        fit: BoxFit.cover,
        // On web, an <img> element loads images from sites without CORS headers.
        webHtmlElementStrategy: WebHtmlElementStrategy.prefer,
        errorBuilder: (_, __, ___) => const DecoratedBox(
            decoration: BoxDecoration(gradient: kHeroGradient)),
        frameBuilder: (_, child, frame, sync) => sync || frame != null
            ? child
            : const DecoratedBox(
                decoration: BoxDecoration(gradient: kHeroGradient)),
      );
}

class _Hero extends StatelessWidget {
  const _Hero();

  @override
  Widget build(BuildContext context) {
    final top = MediaQuery.paddingOf(context).top;
    return SizedBox(
      height: 560 + top,
      child: Stack(fit: StackFit.expand, children: [
        const _SiteImage(SagemakerSite.heroImage),
        const DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [Color(0x660B2F25), Color(0xCC0B2F25), Color(0xFF0B2F25)],
              stops: [0, 0.55, 1],
            ),
          ),
        ),
        Padding(
          padding: EdgeInsets.fromLTRB(22, top + 16, 22, 28),
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const SageMakerLogo(height: 46, color: Colors.white),
            const Spacer(),
            const FadeSlideIn(
              child: Text('GREAT things happen when we make things together.',
                  style: TextStyle(
                      color: kAccent,
                      fontSize: 12,
                      letterSpacing: 1.2,
                      fontWeight: FontWeight.w800)),
            ),
            const SizedBox(height: 10),
            const FadeSlideIn(
              index: 1,
              child: Text(SagemakerSite.tagline,
                  style: TextStyle(
                      fontFamily: kDisplayFont,
                      color: Colors.white,
                      fontSize: 38,
                      height: 1.1,
                      fontWeight: FontWeight.w700)),
            ),
            const SizedBox(height: 12),
            const FadeSlideIn(
              index: 2,
              child: Text(SagemakerSite.intro,
                  style: TextStyle(color: Colors.white70, height: 1.5)),
            ),
            const SizedBox(height: 22),
            FadeSlideIn(
              index: 3,
              child: Row(children: [
                Expanded(
                  child: FilledButton.icon(
                    key: const Key('welcome-shop'),
                    style: FilledButton.styleFrom(
                        backgroundColor: kAccent, foregroundColor: kText),
                    onPressed: () => context.go('/'),
                    icon: const Icon(Icons.storefront_outlined),
                    label: const Text('Start shopping'),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: OutlinedButton(
                    key: const Key('welcome-signin'),
                    style: OutlinedButton.styleFrom(
                        foregroundColor: Colors.white,
                        side: const BorderSide(color: Colors.white70)),
                    onPressed: () => context.push('/login'),
                    child: const Text('Sign in'),
                  ),
                ),
              ]),
            ),
          ]),
        ),
      ]),
    );
  }
}

class _VideoSection extends StatefulWidget {
  const _VideoSection();

  @override
  State<_VideoSection> createState() => _VideoSectionState();
}

class _VideoSectionState extends State<_VideoSection> {
  bool _playing = false;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const SectionHeader('Watch our story'),
      ClipRRect(
        borderRadius: BorderRadius.circular(kRadiusLarge),
        child: AspectRatio(
          aspectRatio: 16 / 9,
          child: _playing
              ? const VimeoPlayer(videoId: SagemakerSite.videoId)
              : Material(
                  color: Colors.black,
                  child: InkWell(
                    key: const Key('welcome-play'),
                    onTap: () => setState(() => _playing = true),
                    child: Stack(fit: StackFit.expand, children: [
                      const _SiteImage(SagemakerSite.communityImage),
                      const ColoredBox(color: Color(0x55000000)),
                      Center(
                        child: Container(
                          width: 74,
                          height: 74,
                          decoration: BoxDecoration(
                            gradient: kGoldGradient,
                            shape: BoxShape.circle,
                            boxShadow: softShadow(0.3),
                          ),
                          child: const Icon(Icons.play_arrow_rounded,
                              size: 46, color: kPrimary),
                        ),
                      ),
                      const Positioned(
                        left: 16,
                        bottom: 14,
                        child: Text(SagemakerSite.tagline,
                            style: TextStyle(
                                color: Colors.white,
                                fontWeight: FontWeight.w700)),
                      ),
                    ]),
                  ),
                ),
        ),
      ),
    ]);
  }
}

class _PillarsSection extends StatelessWidget {
  const _PillarsSection();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const SectionHeader('We develop. We connect. We enable.'),
      Text(
          'SAGEMAKER brings together businesses, product development and local '
          'production capabilities through one connected ecosystem.',
          style: theme.textTheme.bodyMedium?.copyWith(color: kMuted)),
      const SizedBox(height: 16),
      for (final (i, p) in SagemakerSite.pillars.indexed)
        FadeSlideIn(
          index: i,
          child: Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: SoftCard(
              child:
                  Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Container(
                  width: 50,
                  height: 50,
                  decoration: BoxDecoration(
                    gradient: kHeroGradient,
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: Icon(p.$1, color: kAccent),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(p.$2, style: theme.textTheme.titleLarge),
                        Text(p.$3,
                            style: theme.textTheme.titleSmall
                                ?.copyWith(color: kPrimaryLight)),
                        const SizedBox(height: 6),
                        Text(p.$4, style: theme.textTheme.bodyMedium),
                      ]),
                ),
              ]),
            ),
          ),
        ),
    ]);
  }
}

class _ImpactSection extends StatelessWidget {
  const _ImpactSection();

  @override
  Widget build(BuildContext context) {
    return GradientPanel(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text(
            'Every number represents a person, a skill and an opportunity.',
            style: TextStyle(
                fontFamily: kDisplayFont,
                color: Colors.white,
                fontSize: 20,
                height: 1.25,
                fontWeight: FontWeight.w700)),
        const SizedBox(height: 18),
        LayoutBuilder(builder: (context, box) {
          final w = (box.maxWidth - 12) / 2;
          return Wrap(spacing: 12, runSpacing: 16, children: [
            for (final (n, suffix, label) in SagemakerSite.impact)
              SizedBox(
                  width: w,
                  child: _Counter(target: n, suffix: suffix, label: label)),
          ]);
        }),
      ]),
    );
  }
}

class _Counter extends StatelessWidget {
  const _Counter(
      {required this.target, required this.suffix, required this.label});
  final int target;
  final String suffix;
  final String label;

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          TweenAnimationBuilder<double>(
            tween: Tween(begin: 0, end: target.toDouble()),
            duration: const Duration(milliseconds: 1600),
            curve: Curves.easeOutCubic,
            builder: (_, v, __) => Text('${v.round()}$suffix',
                style: const TextStyle(
                    fontFamily: kDisplayFont,
                    color: kAccent,
                    fontSize: 34,
                    fontWeight: FontWeight.w700)),
          ),
          Text(label,
              style: const TextStyle(color: Colors.white70, fontSize: 13)),
        ],
      );
}

class _AccessSection extends StatelessWidget {
  const _AccessSection();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      ClipRRect(
        borderRadius: BorderRadius.circular(kRadiusLarge),
        child: const AspectRatio(
          aspectRatio: 4 / 3,
          child: _SiteImage(SagemakerSite.storyImage),
        ),
      ),
      const SizedBox(height: 18),
      Text(SagemakerSite.accessTitle, style: theme.textTheme.headlineMedium),
      const SizedBox(height: 10),
      for (final p in SagemakerSite.accessBody)
        Padding(
          padding: const EdgeInsets.only(bottom: 10),
          child: Text(p, style: theme.textTheme.bodyLarge),
        ),
      const SizedBox(height: 4),
      Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: const Color(0xFFE8F0EB),
          borderRadius: BorderRadius.circular(kRadiusLarge),
        ),
        child: const Row(children: [
          Icon(Icons.format_quote_rounded, color: kPrimary, size: 30),
          SizedBox(width: 10),
          Expanded(
            child: Text(
                'We are building an ecosystem where local talent can grow, participate and thrive.',
                style: TextStyle(
                    fontWeight: FontWeight.w700, color: kPrimary, height: 1.4)),
          ),
        ]),
      ),
    ]);
  }
}

class _PartnersSection extends StatelessWidget {
  const _PartnersSection();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const SectionHeader('Become part of the mission!'),
      Text('Crafted by visionaries, driven by community.',
          style: theme.textTheme.bodyMedium?.copyWith(color: kMuted)),
      const SizedBox(height: 14),
      for (final (i, p) in SagemakerSite.partners.indexed)
        FadeSlideIn(
          index: i,
          child: Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: SoftCard(
              onTap: () => _open(SagemakerSite.contactUrl),
              child: Row(children: [
                Icon(p.$1, color: kPrimary, size: 30),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(p.$2.toUpperCase(),
                            style: theme.textTheme.labelSmall
                                ?.copyWith(color: kPrimaryLight)),
                        const SizedBox(height: 2),
                        Text(p.$3, style: theme.textTheme.titleSmall),
                      ]),
                ),
                const Icon(Icons.north_east_rounded, color: kMuted),
              ]),
            ),
          ),
        ),
    ]);
  }
}

class _BottomCta extends StatelessWidget {
  const _BottomCta();

  @override
  Widget build(BuildContext context) {
    return GradientPanel(
      gradient: kGoldGradient,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text("Let's make something that matters.",
            style: TextStyle(
                fontFamily: kDisplayFont,
                fontSize: 24,
                color: kText,
                fontWeight: FontWeight.w700)),
        const SizedBox(height: 6),
        const Text(
            'A product. An opportunity. A stronger local economy. It starts with a conversation.',
            style: TextStyle(color: kText, height: 1.4)),
        const SizedBox(height: 16),
        Row(children: [
          Expanded(
            child: FilledButton(
              onPressed: () => context.go('/'),
              child: const Text('Shop the collection'),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: OutlinedButton(
              onPressed: () => _open(SagemakerSite.contactUrl),
              child: const Text('Contact us'),
            ),
          ),
        ]),
        const SizedBox(height: 10),
        Center(
          child: TextButton(
            onPressed: () => _open(SagemakerSite.url),
            child: const Text('Visit sagemaker.asia'),
          ),
        ),
      ]),
    );
  }
}
