#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "FDTimeOfDay.generated.h"

class UDirectionalLightComponent;
class UExponentialHeightFogComponent;
class APostProcessVolume;
class AFDNightLights;
class UMaterialParameterCollection;
class AFDInstances;
class UInputAction;
class UInputMappingContext;
struct FInputActionValue;

/** 太陽の高度ごとの見た目。高度の間は線形に補間する */
USTRUCT(BlueprintType)
struct FFDLookKey
{
	GENERATED_BODY()

	/** 太陽の高度 (度)。地平線が 0、沈んでいるとマイナス */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Look")
	float SunElevationDeg = 0.f;

	/** 露出の中心 (EV100)。自動露出はこの ±ExposureRangeEV の中で動く。小さいほど明るく写る */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Look")
	float ExposureEV100 = 14.f;

	/** 霧の色 (空の散乱光とは別に足される一定の色)。露出に合わせて自動で明るさを変えるので、ここは色味と強さだけ */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Look")
	FLinearColor FogTint = FLinearColor::White;

	/** 太陽の方向の霧の色 (夕日の光芒)。強すぎると画面が白く黄ばむ */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Look")
	FLinearColor SunGlow = FLinearColor::Black;

	/** ボリュメトリックフォグの前方散乱 (0-0.9)。大きいほど太陽のまわりが白く光る */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Look")
	float FogForwardScatter = 0.5f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Look")
	float BloomIntensity = 0.5f;

	/** 彩度 (1 = そのまま) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Look")
	float Saturation = 1.f;

	/** 画面全体の色のかけ算 (夜は青く、夕方は暖かく) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Look")
	FLinearColor ColorGain = FLinearColor::White;
};

/**
 * 時刻 (朝・昼・夕・夜) を切り替える。レベルに1つ置く (無ければ GameMode がプレイ開始時に置く)。
 *
 * - 太陽: 糸島の緯度経度と日付から位置を計算し、SunSky の太陽の向きを直接回す
 * - 月: 夜だけ点く2つ目の平行光源 (大気の2番目の光源なので、空がほのかに青くなり月の円盤も描かれる)
 * - 露出・霧・ブルーム・色: 太陽の高度ごとの表 (Looks) から補間する
 * - 夜: 星空 (空のマテリアル M_FD_Sky) を時刻に合わせて回し、日が沈むと防犯灯 (FDNightLights) を点ける。
 *   空と防犯灯のマテリアルへは MPC_FD_Night で値を渡す
 *
 * 操作: T を押している間は時間が進み、G で戻る。1 = 朝、2 = 昼、3 = 夕方、4 = 夜 (数秒かけて進む)。
 */
UCLASS()
class FUKUOKADRIVE_API AFDTimeOfDay : public AActor
{
	GENERATED_BODY()

public:
	AFDTimeOfDay();

	virtual void Tick(float DeltaSeconds) override;

	/** 時刻 (時、0-24)。日本時間 */
	UFUNCTION(BlueprintCallable, Category = "TimeOfDay")
	void SetHour(float NewHour);

	UFUNCTION(BlueprintPure, Category = "TimeOfDay")
	float GetHour() const { return Hour; }

	/** 指定の時刻まで、TransitionSeconds かけて時間を先へ進める */
	UFUNCTION(BlueprintCallable, Category = "TimeOfDay")
	void GoToHour(float TargetHour);

	UFUNCTION(BlueprintPure, Category = "TimeOfDay")
	float GetSunElevationDeg() const { return SunElevationDeg; }

	// --- 時刻 ---

	/** 開始時刻。マイナスなら SunSky の SolarTime (setup_project.py の SOLAR_TIME) を使う */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TimeOfDay")
	float StartHour = -1.f;

	/** 何もしないときの時間の流れ (ゲーム内の時間 / 実時間)。0 なら止まったまま、60 なら1分で1時間 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TimeOfDay")
	float TimeScale = 0.f;

	/** T / G を押している間、実時間1秒で進む時間 (時) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TimeOfDay")
	float ScrubHoursPerSecond = 1.5f;

	/** 1-4 キーで時刻を移すのにかける秒数 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TimeOfDay")
	float TransitionSeconds = 4.f;

	/** 1-4 キーの時刻 (朝・昼・夕方・夜)。朝・夕方・夜はその日の日の出・日の入りからの時間 (時) で、
	 *  日付 (Y キーの季節) が変わっても同じ見え方の時刻になる。昼だけは時刻そのもの */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TimeOfDay")
	float MorningAfterSunriseHours = 0.6f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TimeOfDay")
	float NoonHour = 12.5f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TimeOfDay")
	float SunsetBeforeSunsetHours = 0.35f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TimeOfDay")
	float NightAfterSunsetHours = 2.0f;

	/** Y キーで順に切り替える日付 (X = 月、Y = 日)。夏至・秋分・冬至・春分 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TimeOfDay|Place")
	TArray<FIntPoint> SeasonDates = {FIntPoint(6, 21), FIntPoint(9, 23), FIntPoint(12, 21), FIntPoint(3, 20)};

	// --- 場所と日付 (setup_project.py と同じ値) ---

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TimeOfDay|Place")
	float Latitude = 33.641f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TimeOfDay|Place")
	float Longitude = 130.196f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TimeOfDay|Place")
	float TimeZone = 9.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TimeOfDay|Place")
	int32 Month = 6;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TimeOfDay|Place")
	int32 Day = 21;

	// --- 月 ---

	/** 月の方位 (度、北から時計回り)。二見ヶ浦は西に海が開けているので、海に月の光の道ができる西寄り */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TimeOfDay|Moon")
	float MoonAzimuthDeg = 280.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TimeOfDay|Moon")
	float MoonElevationDeg = 28.f;

	/** 太陽の明るさ (lux)。SunSky の既定値。日没後はこれを弱めて使う
	 *  (ライトの値を読み戻すと、夜に保存したときに暗いまま残るので、ここに持つ) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TimeOfDay")
	float SunLux = 75000.f;

	/** 満月の明るさ (lux)。実際は 0.1-0.3 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TimeOfDay|Moon")
	float MoonLux = 0.3f;

	// --- 夜 ---

	/** 星空・防犯灯の光る面へ値を渡すパラメータ (setup_project.py が作る) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TimeOfDay|Night")
	TSoftObjectPtr<UMaterialParameterCollection> NightParameters =
		TSoftObjectPtr<UMaterialParameterCollection>(FSoftObjectPath(TEXT("/Game/FukuokaDrive/Materials/MPC_FD_Night.MPC_FD_Night")));

	/** 0 等星の明るさ (cd/m2)。暗い星ほど 1 等級ごとに 1/2.5 になる */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TimeOfDay|Night")
	float StarBrightness = 14.f;

	/** 天の川の明るさ (cd/m2) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TimeOfDay|Night")
	float MilkyWayBrightness = 0.12f;

	/** 東の空 (福岡市) と南の空 (前原) の街明かりの明るさ (cd/m2) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TimeOfDay|Night")
	float CityGlowBrightness = 0.3f;

	/** 防犯灯が点く太陽の高度 (度)。この高度から下へ NightLightsFadeDeg の間で明るくなる */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TimeOfDay|Night")
	float NightLightsOnBelowDeg = 1.5f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TimeOfDay|Night")
	float NightLightsFadeDeg = 3.f;

	/** 家の窓が灯り始める太陽の高度 (度)。ここから HouseLightsFadeDeg 下までに、その時刻の割合まで灯る */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TimeOfDay|Night")
	float HouseLightsOnBelowDeg = 2.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TimeOfDay|Night")
	float HouseLightsFadeDeg = 6.f;

	/** 暗いときに灯っている家の窓の割合 (0 時から 23 時まで 1 時間ごと、間は補間)。夕食どきが多く、夜更けは少ない */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TimeOfDay|Night")
	TArray<float> HouseLightsByHour = {
		0.16f, 0.10f, 0.06f, 0.05f, 0.06f, 0.14f, 0.30f, 0.28f, 0.15f, 0.12f, 0.12f, 0.12f,
		0.12f, 0.12f, 0.12f, 0.12f, 0.30f, 0.45f, 0.58f, 0.65f, 0.65f, 0.58f, 0.45f, 0.28f};

	/** 日没後、太陽の光を弱め始める高度 (度)。ここから -12° (消える高度) までに少しずつ暗くする */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TimeOfDay|Night")
	float SunFadeStartDeg = -4.f;

	/** -12° までに太陽の光を何桁暗くするか (2.5 なら約 1/300)。
	 *  UE の大気は太陽が深く沈んでも空が明るく残るので、実際の薄明のように指数的に暗くする */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TimeOfDay|Night")
	float SunFadeDecades = 2.5f;

	// --- 見た目 ---

	/** 太陽の高度ごとの見た目。高度の低い順に並べる */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TimeOfDay|Look")
	TArray<FFDLookKey> Looks;

	/** 自動露出が明るさに慣れる速さ (EV/秒)。遅いと、昼から夜へ時刻を移したあと 20 秒ほど白っぽいまま */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TimeOfDay|Look")
	float ExposureAdaptSpeed = 4.f;

	/** 自動露出が動ける幅 (EV、中心から上下に) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TimeOfDay|Look")
	float ExposureRangeEV = 1.f;

	/** 朝 (3-11時) の日の出前後に霧を濃くする倍率。1 なら朝もやなし */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TimeOfDay|Look")
	float MorningMistScale = 2.5f;

	/** 画面左上に時刻を表示する */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TimeOfDay")
	bool bShowDebugText = true;

protected:
	virtual void BeginPlay() override;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components")
	TObjectPtr<UDirectionalLightComponent> MoonLight;

private:
	void FindSceneActors();
	void CreateInput();
	void ComputeSun(float InHour, float& OutAzimuthDeg, float& OutElevationDeg) const;
	/** その日の日の出と日の入りの時刻 (時)。太陽の上端が地平線に重なるとき (高度 -0.83°) */
	void ComputeSunriseSunset(float& OutSunrise, float& OutSunset) const;
	float PresetHour(int32 Index) const;
	void NextSeason();
	/** 季節の花と桜 (AFDInstances) を、いまの日付の季節のものだけ見せる */
	void ApplySeason();
	FFDLookKey EvaluateLook(float Elevation) const;
	void Apply();
	void ApplyNight();
	/** 地方恒星時 (ラジアン、0-2π)。星空をこの角度だけ天の北極のまわりに回す */
	float ComputeLocalSiderealAngle(float InHour) const;

	/** HouseLightsByHour を InHour で補間した値 */
	float HouseLightsShare(float InHour) const;

	/** 方位 (北から東回り) と高度から UE の向き。GridRotationDeg だけ北を回す */
	FVector DirectionFromAzEl(float AzimuthDeg, float ElevationDeg) const;

	/** コースの升目の回転 (度)。AFDCourseInfo から読む */
	float GridRotationDeg = 0.f;

	UPROPERTY(Transient)
	TObjectPtr<UDirectionalLightComponent> SunLight;

	UPROPERTY(Transient)
	TObjectPtr<UExponentialHeightFogComponent> Fog;

	UPROPERTY(Transient)
	TObjectPtr<APostProcessVolume> PostProcess;

	UPROPERTY(Transient)
	TArray<TObjectPtr<AFDNightLights>> NightLights;

	UPROPERTY(Transient)
	TArray<TObjectPtr<AFDInstances>> SeasonalInstances;

	UPROPERTY(Transient)
	TObjectPtr<UMaterialParameterCollection> NightCollection;

	UPROPERTY(Transient)
	TObjectPtr<UInputMappingContext> MappingContext;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> ScrubAction;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UInputAction>> PresetActions;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> SeasonAction;

	float Hour = 19.2f;
	float SunElevationDeg = 0.f;
	float ScrubInput = 0.f;
	float BaseFogDensity = 0.003f;

	// 1-4 キーでの移動中
	bool bTransitioning = false;
	float TransitionRemainingHours = 0.f;
	float TransitionRateHoursPerSecond = 0.f;
};
