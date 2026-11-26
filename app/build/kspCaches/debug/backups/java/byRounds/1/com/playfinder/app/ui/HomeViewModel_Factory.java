package com.playfinder.app.ui;

import com.playfinder.app.data.PlayFinderRepository;
import dagger.internal.DaggerGenerated;
import dagger.internal.Factory;
import dagger.internal.QualifierMetadata;
import dagger.internal.ScopeMetadata;
import javax.annotation.processing.Generated;
import javax.inject.Provider;

@ScopeMetadata
@QualifierMetadata
@DaggerGenerated
@Generated(
    value = "dagger.internal.codegen.ComponentProcessor",
    comments = "https://dagger.dev"
)
@SuppressWarnings({
    "unchecked",
    "rawtypes",
    "KotlinInternal",
    "KotlinInternalInJava",
    "cast",
    "deprecation"
})
public final class HomeViewModel_Factory implements Factory<HomeViewModel> {
  private final Provider<PlayFinderRepository> repoProvider;

  public HomeViewModel_Factory(Provider<PlayFinderRepository> repoProvider) {
    this.repoProvider = repoProvider;
  }

  @Override
  public HomeViewModel get() {
    return newInstance(repoProvider.get());
  }

  public static HomeViewModel_Factory create(Provider<PlayFinderRepository> repoProvider) {
    return new HomeViewModel_Factory(repoProvider);
  }

  public static HomeViewModel newInstance(PlayFinderRepository repo) {
    return new HomeViewModel(repo);
  }
}
