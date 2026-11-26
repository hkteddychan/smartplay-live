package com.playfinder.app.data;

import com.playfinder.app.data.local.dao.SlotDao;
import com.playfinder.app.data.remote.LcsdApi;
import dagger.internal.DaggerGenerated;
import dagger.internal.Factory;
import dagger.internal.QualifierMetadata;
import dagger.internal.ScopeMetadata;
import javax.annotation.processing.Generated;
import javax.inject.Provider;

@ScopeMetadata("javax.inject.Singleton")
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
public final class PlayFinderRepository_Factory implements Factory<PlayFinderRepository> {
  private final Provider<LcsdApi> apiProvider;

  private final Provider<SlotDao> slotDaoProvider;

  public PlayFinderRepository_Factory(Provider<LcsdApi> apiProvider,
      Provider<SlotDao> slotDaoProvider) {
    this.apiProvider = apiProvider;
    this.slotDaoProvider = slotDaoProvider;
  }

  @Override
  public PlayFinderRepository get() {
    return newInstance(apiProvider.get(), slotDaoProvider.get());
  }

  public static PlayFinderRepository_Factory create(Provider<LcsdApi> apiProvider,
      Provider<SlotDao> slotDaoProvider) {
    return new PlayFinderRepository_Factory(apiProvider, slotDaoProvider);
  }

  public static PlayFinderRepository newInstance(LcsdApi api, SlotDao slotDao) {
    return new PlayFinderRepository(api, slotDao);
  }
}
