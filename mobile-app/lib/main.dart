import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import 'screens/home_screen.dart';
import 'screens/submit_report_screen.dart';
import 'screens/privacy_notice_screen.dart';
import 'screens/confirmation_screen.dart';
import 'services/report_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Lock to portrait for consistent UX
  await SystemChrome.setPreferredOrientations([
    DeviceOrientation.portraitUp,
    DeviceOrientation.portraitDown,
  ]);

  runApp(const AnonymousSignalApp());
}

class AnonymousSignalApp extends StatelessWidget {
  const AnonymousSignalApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => ReportService()),
      ],
      child: MaterialApp(
        title: 'Anonymous Signal',
        debugShowCheckedModeBanner: false,
        theme: _buildTheme(),
        darkTheme: _buildDarkTheme(),
        themeMode: ThemeMode.system,
        initialRoute: '/privacy',
        routes: {
          '/privacy': (ctx) => const PrivacyNoticeScreen(),
          '/home': (ctx) => const HomeScreen(),
          '/submit': (ctx) => const SubmitReportScreen(),
          '/confirmation': (ctx) => const ConfirmationScreen(),
        },
      ),
    );
  }

  ThemeData _buildTheme() {
    return ThemeData(
      useMaterial3: true,
      colorScheme: ColorScheme.fromSeed(
        seedColor: const Color(0xFF1A73E8),
        brightness: Brightness.light,
      ),
      appBarTheme: const AppBarTheme(
        centerTitle: true,
        elevation: 0,
        backgroundColor: Colors.white,
        foregroundColor: Color(0xFF1A1A2E),
        titleTextStyle: TextStyle(
          fontFamily: 'SF Pro Display',
          fontSize: 18,
          fontWeight: FontWeight.w600,
          color: Color(0xFF1A1A2E),
        ),
      ),
      cardTheme: CardTheme(
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: BorderSide(color: Colors.grey.shade200),
        ),
      ),
    );
  }

  ThemeData _buildDarkTheme() {
    return ThemeData(
      useMaterial3: true,
      colorScheme: ColorScheme.fromSeed(
        seedColor: const Color(0xFF1A73E8),
        brightness: Brightness.dark,
      ),
    );
  }
}
