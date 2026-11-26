package com.playfinder.app.di;

import com.playfinder.app.data.remote.LcsdApi;
import dagger.internal.DaggerGenerated;
import dagger.internal.Factory;
import dagger.internal.Preconditions;
import dagger.internal.QualifierMetadata;
import dagger.internal.ScopeMetadata;
import javax.annotation.processing.Generated;
import javax.inject.Provider;
import retrofit2.Retrofit;

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
public final class NetworkModule_ProvideLcsdApiFactory implements Factory<LcsdApi> {
  private final Provider<Retrofit> retrofitProvider;

  public NetworkModule_ProvideLcsdApiFactory(Provider<Retrofit> retrofitProvider) {
    this.retrofitProvider = retrofitProvider;
  }

  @Override
  public LcsdApi get() {
    return provideLcsdApi(retrofitProvider.get());
  }

  public static NetworkModule_ProvideLcsdApiFactory create(Provider<Retrofit> retrofitProvider) {
    return new NetworkModule_ProvideLcsdApiFactory(retrofitProvider);
  }

  public static LcsdApi provideLcsdApi(Retrofit retrofit) {
    return Preconditions.checkNotNullFromProvides(NetworkModule.INSTANCE.provideLcsdApi(retrofit));
  }
}
