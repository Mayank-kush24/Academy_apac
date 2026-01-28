//
//  DashboardView.swift
//  GenAIAcademyDashboard
//
//  Main dashboard screen with KPI cards and charts
//

import SwiftUI

struct DashboardView: View {
    @StateObject private var viewModel = DashboardViewModel()
    @StateObject private var authService = AuthService.shared
    
    var body: some View {
        NavigationView {
            ZStack {
                // Background
                Color(uiColor: .systemGroupedBackground)
                    .ignoresSafeArea()
                
                if viewModel.isLoading && viewModel.summary == nil {
                    LoadingView()
                } else if let errorMessage = viewModel.errorMessage, viewModel.summary == nil {
                    ErrorView(message: errorMessage) {
                        Task {
                            await viewModel.loadDashboardData()
                        }
                    }
                } else {
                    ScrollView {
                        VStack(spacing: 24) {
                            // Period Selector
                            periodSelector
                            
                            // KPI Cards Grid
                            if let summary = viewModel.summary {
                                kpiCardsGrid(summary: summary)
                            }
                            
                            // Optional: Add charts here in future
                        }
                        .padding()
                    }
                    .refreshable {
                        await viewModel.refresh()
                    }
                }
            }
            .navigationTitle("Dashboard")
            .navigationBarTitleDisplayMode(.large)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Menu {
                        Button(action: {
                            Task {
                                await viewModel.refresh()
                            }
                        }) {
                            Label("Refresh", systemImage: "arrow.clockwise")
                        }
                        
                        Divider()
                        
                        Button(role: .destructive, action: {
                            authService.logout()
                        }) {
                            Label("Logout", systemImage: "rectangle.portrait.and.arrow.right")
                        }
                    } label: {
                        Image(systemName: "ellipsis.circle")
                    }
                }
            }
        }
        .task {
            await viewModel.loadDashboardData()
        }
    }
    
    // MARK: - Period Selector
    private var periodSelector: some View {
        HStack(spacing: 12) {
            ForEach(DashboardViewModel.Period.allCases, id: \.self) { period in
                Button(action: {
                    Task {
                        await viewModel.changePeriod(period)
                    }
                }) {
                    Text(period.displayName)
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(viewModel.selectedPeriod == period ? .white : .primary)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 8)
                        .background(
                            RoundedRectangle(cornerRadius: 20)
                                .fill(viewModel.selectedPeriod == period ?
                                      LinearGradient(colors: [.blue, .purple], startPoint: .leading, endPoint: .trailing) :
                                      LinearGradient(colors: [.clear], startPoint: .leading, endPoint: .trailing)
                                )
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: 20)
                                .stroke(Color.gray.opacity(0.2), lineWidth: 1)
                        )
                }
            }
        }
        .padding(.horizontal)
    }
    
    // MARK: - KPI Cards Grid
    private func kpiCardsGrid(summary: DashboardSummary) -> some View {
        LazyVGrid(columns: [
            GridItem(.flexible(), spacing: 16),
            GridItem(.flexible(), spacing: 16)
        ], spacing: 16) {
            KPICardView(
                title: "Total Users",
                value: "\(summary.totalUsers)",
                gradientColors: [.blue, .cyan]
            )
            
            KPICardView(
                title: "Organizations",
                value: "\(summary.uniqueOrganizations)",
                gradientColors: [.purple, .pink]
            )
            
            KPICardView(
                title: "Top Domain",
                value: summary.topDomain,
                subtitle: "Primary sector",
                gradientColors: [.orange, .red]
            )
            
            KPICardView(
                title: "Top City",
                value: summary.topCity,
                subtitle: "Leading region",
                gradientColors: [.green, .mint]
            )
        }
    }
}

#Preview {
    DashboardView()
}
