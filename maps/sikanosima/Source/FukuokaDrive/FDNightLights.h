#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "FDNightLights.generated.h"

class USpotLightComponent;

/**
 * 夜に点く光源 (電柱の防犯灯) をまとめて置くアクター。tools/ue/setup_project.py が光源の位置と向きを入れる。
 * 光源 (スポットライト) は保存せず、プレイ開始時 (とエディタで置き直したとき) に作る。
 * 点け消しは FDTimeOfDay が太陽の高度に合わせて SetOnAmount で行う。光る面の明るさはマテリアル (MPC_FD_Night の NightLights) が変える。
 */
UCLASS()
class FUKUOKADRIVE_API AFDNightLights : public AActor
{
	GENERATED_BODY()

public:
	AFDNightLights();

	virtual void OnConstruction(const FTransform& Transform) override;

	/** 点き具合 (0 = 消灯、1 = 点灯) */
	UFUNCTION(BlueprintCallable, Category = "NightLights")
	void SetOnAmount(float Amount);

	/** 光源の位置と向き (ワールド座標)。光は +X の方向へ出る */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "NightLights")
	TArray<FTransform> Lights;

	/** 1つの明るさ (lm)。LED の防犯灯は 1000-3000 lm くらい */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "NightLights")
	float Intensity = 2500.f;

	/** 色温度 (K)。LED の防犯灯は昼白色 (5000K) が多い */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "NightLights")
	float Temperature = 4800.f;

	/** 光の届く距離 (cm) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "NightLights")
	float AttenuationRadius = 2400.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "NightLights")
	float InnerConeAngle = 40.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "NightLights")
	float OuterConeAngle = 72.f;

	/** カメラからこれより遠い光源は描かない (cm)。数百個あっても重くならないように */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "NightLights")
	float MaxDrawDistance = 30000.f;

	/** 霧の中に光の筋が見える強さ (ボリュメトリックフォグ) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "NightLights")
	float VolumetricScattering = 1.f;

	/** 影を落とすか。数が多いので既定は落とさない */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "NightLights")
	bool bCastShadows = false;

	/** エディタで見るときの点き具合 (プレイ中は FDTimeOfDay が決める) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "NightLights")
	float EditorOnAmount = 0.f;

protected:
	virtual void BeginPlay() override;

private:
	void BuildLights();
	void ApplyOnAmount();

	UPROPERTY(Transient)
	TArray<TObjectPtr<USpotLightComponent>> Spots;

	/** 点き具合 (SetOnAmount で決めた値) と、光源に入れた値 */
	float OnAmount = 0.f;
	float AppliedAmount = -1.f;
};
